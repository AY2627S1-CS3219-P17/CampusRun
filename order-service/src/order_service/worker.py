# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated order-worker entry point, following credit-service/worker.py: connects to the database and
#        RabbitMQ, checks the reply queue is reachable, and stops cleanly on SIGTERM; AI-added the outbox relay,
#        the reply consumer and the sweeper loops (2026-10-19).
# Author review: <to be completed by author>

"""order-worker: the order service's background process. It runs three loops side by side:

    1. the outbox relay, which publishes the credit commands written by the API (outbox.py)
    2. the consumer of the credit service's ReservationResult replies (below)
    3. the sweeper, which expires errands past their deadline and resends stuck credit commands (sweeper.py)

If one of them fails, the others are stopped and the process exits, so Compose restarts it.

For each reply:
    1. check it: type ReservationResult, sent by the credit-service login, with a valid body
    2. apply it in one database transaction (credit.apply_reply), retrying while the database is unavailable
    3. acknowledge it, only after that transaction has committed

A crash before the acknowledgement leaves the reply in the queue, and applying it again changes nothing. A reply that
fails the check, or keeps failing for an unexpected reason, is rejected without requeueing. The reply queue has no
dead-letter queue, so it's dropped; nothing is lost for good, because the reconciler resends the command once the
errand's credits have been PENDING for RECONCILE_AFTER_MINUTES, and the Credit Service replies again.
"""

import asyncio
import logging
import signal

from aio_pika.abc import AbstractIncomingMessage, AbstractQueue
from aio_pika.exceptions import AMQPError
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.broker import connect
from order_service.config import Settings, get_settings
from order_service.credit import REPLY_TYPE, ReservationResult, apply_reply
from order_service.db import create_engine
from order_service.outbox import OutboxRelay, RabbitPublisher
from order_service.sweeper import Sweeper

log = logging.getLogger("order_service.worker")

# Created by rabbitmq/definitions.json; this service's RabbitMQ user may read it but not create or change it
REPLY_QUEUE = "order-service.credit-replies"
# The only login allowed to reply. RabbitMQ refuses a publish whose user_id doesn't match the sender's login, so it
# can't be forged.
CREDIT_SERVICE_USER = "credit-service"
MAX_UNEXPECTED_FAILURES = 3
# Postgres error codes for "try again": serialization failure, deadlock
RETRYABLE_SQLSTATES = {"40001", "40P01"}


class InvalidReply(Exception):
    pass


def parse(message: AbstractIncomingMessage) -> ReservationResult:
    if message.type != REPLY_TYPE:
        raise InvalidReply(f"unexpected message type {message.type!r}")
    if message.user_id != CREDIT_SERVICE_USER:
        raise InvalidReply(f"sent by {message.user_id!r}, not {CREDIT_SERVICE_USER!r}")
    try:
        return ReservationResult.model_validate_json(message.body)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'body'}: {e['msg']}" for e in exc.errors())
        raise InvalidReply(f"invalid body: {details}") from None


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


async def apply_with_retries(engine: AsyncEngine, reply: ReservationResult, *, retry_delay: float = 0.5) -> str:
    unexpected = 0
    delay = retry_delay
    while True:
        try:
            async with engine.begin() as conn:
                return await apply_reply(conn, reply)
        except Exception as exc:
            if is_transient(exc):
                # Keep holding the reply: no other worker could apply it while the database is down either
                log.warning("Database unavailable or busy (%s); retrying in %.1fs", type(exc).__name__, delay)
            else:
                unexpected += 1
                if unexpected >= MAX_UNEXPECTED_FAILURES:
                    raise
                log.exception("Unexpected error applying the reply for errand %s (attempt %d)", reply.errand_id, unexpected)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def process(message: AbstractIncomingMessage, engine: AsyncEngine, *, retry_delay: float = 0.5) -> None:
    # correlation_id is the message_id of the command this replies to, so a command can be traced to its reply
    trace = f"reply {message.message_id} to command {message.correlation_id}"
    try:
        reply = parse(message)
    except InvalidReply as exc:
        log.warning("Dropping %s from %r: %s", trace, message.user_id, exc)
        await message.reject(requeue=False)
        return

    try:
        outcome = await apply_with_retries(engine, reply, retry_delay=retry_delay)
    except Exception:
        log.exception(
            "Dropping %s for errand %s after %d failures; the reconciler will resend the command",
            trace,
            reply.errand_id,
            MAX_UNEXPECTED_FAILURES,
        )
        await message.reject(requeue=False)
        return

    log.info(
        "Errand %s %s: %s%s -> %s",
        reply.errand_id,
        trace,
        reply.status,
        f" ({reply.rejection})" if reply.rejection else "",
        outcome,
    )
    # Last: until this, a crash means RabbitMQ delivers the reply again
    await message.ack()


async def consume(queue: AbstractQueue, engine: AsyncEngine) -> None:
    log.info("Waiting for credit replies on %s", queue.name)
    async with queue.iterator() as messages:
        async for message in messages:
            try:
                await process(message, engine)
            except AMQPError as exc:
                # The connection dropped mid-way. The reply wasn't acknowledged, so RabbitMQ delivers it again after
                # the robust connection reconnects, and the repeat changes nothing.
                log.warning("Lost the broker connection while handling reply %s (%s)", message.message_id, exc)


async def run(settings: Settings) -> None:
    engine = create_engine(settings)
    connection = await connect(settings.rabbitmq_url)
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.worker_prefetch)
        # Looked up, not declared, like credit-worker does with its own queue
        queue = await channel.get_queue(REPLY_QUEUE, ensure=True)
        relay = OutboxRelay(engine, RabbitPublisher(connection))
        sweeper = Sweeper(engine, settings.sweep_seconds)
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(relay.run(), name="outbox relay")
            tasks.create_task(consume(queue, engine), name="reply consumer")
            tasks.create_task(sweeper.run(), name="sweeper")
    finally:
        await connection.close()
        await engine.dispose()


async def _main() -> None:
    task = asyncio.current_task()
    assert task is not None
    loop = asyncio.get_running_loop()
    # PID 1 in a container ignores SIGTERM unless it handles it. Stopping mid-reply is safe: the transaction rolls
    # back and the unacknowledged reply is delivered again.
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
