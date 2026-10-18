# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for RabbitMQ consumer that validates each command's sender and body, applies it in one database
#        transaction with retries, replies, then acknowledges; malformed or unauthorised messages are dead-lettered.
# Author review: <to be completed by author>

"""credit-worker: applies every balance change, one RabbitMQ message at a time.

For each message:
    1. check it: a known command type, sent by a service allowed to send it, with a valid body
    2. apply it in one database transaction (ledger.apply), retrying while the database is unavailable
    3. publish the reply, with a publisher confirm, so the broker has it before going on
    4. acknowledge the command

The command is acknowledged last, so a crash at any step leaves it in the queue and RabbitMQ delivers it again.
Every command is idempotent, so applying it again changes nothing and just repeats the reply: at-least-once
delivery plus idempotent handling gives an effect that happens exactly once.

Where a message ends up:
    - invalid (unknown type, wrong sender, bad body), or contradicts the data   -> dead-letter queue at once
    - the database is down or busy                                             -> held and retried until it's back
    - an unexpected error, MAX_UNEXPECTED_FAILURES times in a row               -> dead-letter queue
    - the worker crashes while holding it                                      -> redelivered; dead-lettered by
                                                                                  RabbitMQ after 5 redeliveries
Nothing is ever requeued with nack: RabbitMQ 4 doesn't count those towards the delivery limit, so a bad message
would loop forever.
"""

import asyncio
import logging
import signal
import uuid

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from credit_service import ledger
from credit_service.broker import connect
from credit_service.commands import COMMAND_QUEUE, COMMANDS, REPLY_EXCHANGE, REPLY_TYPE, Command, CommandSpec
from credit_service.config import Settings, get_settings
from credit_service.db import create_engine

log = logging.getLogger("credit_service.worker")

MAX_UNEXPECTED_FAILURES = 3
# Postgres error codes for "try again": serialization failure, deadlock
RETRYABLE_SQLSTATES = {"40001", "40P01"}


class InvalidMessage(Exception):
    pass


def parse(message: AbstractIncomingMessage) -> tuple[CommandSpec, Command]:
    spec = COMMANDS.get(message.type or "")
    if spec is None:
        raise InvalidMessage(f"unknown command type {message.type!r}")
    # RabbitMQ has already checked that user_id matches the sender's login, so it can't be forged
    if message.user_id not in spec.senders:
        raise InvalidMessage(f"{message.type} may not be sent by {message.user_id!r}")
    if message.routing_key != spec.routing_key:
        raise InvalidMessage(f"{message.type} arrived with routing key {message.routing_key!r}")
    if not message.message_id or len(message.message_id) > 64:
        raise InvalidMessage("message_id is missing or longer than 64 characters")
    try:
        return spec, spec.model.model_validate_json(message.body)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'body'}: {e['msg']}" for e in exc.errors())
        raise InvalidMessage(f"invalid body: {details}") from None


def is_transient(exc: BaseException) -> bool:
    """Errors that clear up by themselves: the database restarting or unreachable, or a lock conflict."""
    if isinstance(exc, (OSError, TimeoutError)):
        return True
    if isinstance(exc, DBAPIError):
        if exc.connection_invalidated or isinstance(exc, (OperationalError, InterfaceError)):
            return True
        code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
        return code in RETRYABLE_SQLSTATES
    return False


async def apply_with_retries(engine: AsyncEngine, command: Command, message_id: str, settings: Settings):
    unexpected = 0
    delay = 0.5
    while True:
        try:
            async with engine.begin() as conn:
                return await ledger.apply(
                    conn, command, message_id=message_id, initial_credits=settings.initial_credits
                )
        except ledger.InvalidCommand:
            raise
        except Exception as exc:
            if is_transient(exc):
                # Keep holding the message: there's no point giving it to another worker while the database is down
                log.warning("Database unavailable or busy (%s); retrying in %.1fs", type(exc).__name__, delay)
            else:
                unexpected += 1
                if unexpected >= MAX_UNEXPECTED_FAILURES:
                    raise
                log.exception("Unexpected error applying %s (attempt %d); retrying", type(command).__name__, unexpected)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def process(
    message: AbstractIncomingMessage, engine: AsyncEngine, replies: AbstractExchange, own_user: str, settings: Settings
) -> None:
    try:
        spec, command = parse(message)
    except InvalidMessage as exc:
        log.warning("Dead-lettering message %s from %r: %s", message.message_id, message.user_id, exc)
        await message.reject(requeue=False)
        return

    try:
        result = await apply_with_retries(engine, command, message.message_id or "", settings)
    except ledger.InvalidCommand as exc:
        log.error("Dead-lettering %s %s: %s", message.type, message.message_id, exc)
        await message.reject(requeue=False)
        return
    except Exception:
        log.exception("Dead-lettering %s %s after %d failures", message.type, message.message_id, MAX_UNEXPECTED_FAILURES)
        await message.reject(requeue=False)
        return

    log.info("Applied %s %s: %s", message.type, message.message_id, _describe(command, result))

    if spec.replies:
        assert not isinstance(result, bool)
        await replies.publish(
            aio_pika.Message(
                result.model_dump_json(by_alias=True).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                type=REPLY_TYPE,
                message_id=str(uuid.uuid4()),
                correlation_id=message.message_id,
                # Lets the receiver check, like this worker does, that the reply really came from this service
                user_id=own_user,
                app_id="credit-service",
            ),
            # Addressed back to whoever sent the command
            routing_key=message.user_id or "",
        )
    # Last: until this, a crash means RabbitMQ delivers the command again
    await message.ack()


def _describe(command: Command, result) -> str:
    fields = command.model_dump(by_alias=True)
    if isinstance(result, bool):
        return f"{fields} -> {'created' if result else 'already existed'}"
    return f"{fields} -> {result.status}, amount {result.amount}" + (f", {result.rejection}" if result.rejection else "")


async def run(settings: Settings) -> None:
    engine = create_engine(settings)
    connection = await connect(settings.rabbitmq_url)
    try:
        channel = await connection.channel(publisher_confirms=True)
        await channel.set_qos(prefetch_count=settings.worker_prefetch)
        # Looked up, not declared: rabbitmq/definitions.json creates them with their dead-letter settings,
        # and this service's RabbitMQ user isn't allowed to create or change them
        queue = await channel.get_queue(COMMAND_QUEUE, ensure=True)
        replies = await channel.get_exchange(REPLY_EXCHANGE, ensure=True)
        own_user = connection.url.user or "credit-service"
        log.info("Waiting for commands on %s", COMMAND_QUEUE)

        async with queue.iterator() as messages:
            async for message in messages:
                try:
                    await process(message, engine, replies, own_user, settings)
                except aio_pika.exceptions.AMQPError as exc:
                    # The connection dropped mid-way. The command wasn't acknowledged, so RabbitMQ delivers it again
                    # after the robust connection reconnects, and the repeat is harmless.
                    log.warning("Lost the broker connection while handling %s (%s)", message.message_id, exc)
    finally:
        await connection.close()
        await engine.dispose()


async def _main() -> None:
    task = asyncio.current_task()
    assert task is not None
    loop = asyncio.get_running_loop()
    # PID 1 in a container ignores SIGTERM unless it handles it. Stopping mid-message is safe: the transaction
    # rolls back and the unacknowledged command is delivered again.
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        await run(get_settings())
    except asyncio.CancelledError:
        log.info("Stopped")


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # aiormq logs every reconnect attempt at length; the worker's own warnings say enough
    logging.getLogger("aiormq").setLevel(logging.CRITICAL)
    logging.getLogger("aio_pika.tools").setLevel(logging.CRITICAL)
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    asyncio.run(_main())
