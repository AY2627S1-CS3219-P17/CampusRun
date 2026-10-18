# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: Transactional outbox generalised from user-service/outbox.py: enqueueing the four credit commands with the
#        change that causes them, and the relay that publishes them to RabbitMQ with publisher confirms.
# Author review: <to be completed by author>

"""Credit commands from this service to the Credit Service, sent reliably.

Publishing straight to RabbitMQ from a request has a gap either way: publish after the commit, and a crash or a
broker outage in between loses the command (an errand whose credits are never reserved); publish before it, and a
rollback leaves a command for an errand that doesn't exist.

So a command is written to the outbox table in the same transaction as the change (enqueue), and OutboxRelay in
order-worker publishes it afterwards, retrying until RabbitMQ confirms it. A command can be published more than once
(a crash after the publish but before marking it), which is fine because every credit command is idempotent.
Commands are published in the order they were written, so an errand's ReleaseCredits never overtakes its
ReserveCredits on the way to the broker.
"""

import asyncio
import json
import logging
from typing import Any, Protocol

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection
from pamqp.commands import Basic
from sqlalchemy import Row, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from order_service.tables import outbox

log = logging.getLogger(__name__)

CREDIT_COMMANDS = "credit.commands"
# The credit service's contract (credit_service/commands.py). The broker only lets this service's login publish
# these routing keys (rabbitmq/definitions.json).
ROUTING_KEYS = {
    "ReserveCredits": "reservation.reserve",
    "AdjustReservation": "reservation.adjust",
    "TransferCredits": "reservation.transfer",
    "ReleaseCredits": "reservation.release",
}


async def enqueue(conn: AsyncConnection, command: str, payload: dict[str, Any]) -> None:
    """Sends a credit command (camelCase body) once this transaction commits."""
    try:
        routing_key = ROUTING_KEYS[command]
    except KeyError:
        raise ValueError(f"{command!r} is not a credit command") from None
    await conn.execute(
        insert(outbox).values(
            exchange=CREDIT_COMMANDS, routing_key=routing_key, message_type=command, payload=payload
        )
    )


class Publisher(Protocol):
    async def publish(self, row: Row) -> None: ...


class RabbitPublisher:
    """Publishes outbox rows on the worker's RabbitMQ connection, with publisher confirms."""

    def __init__(self, connection: AbstractRobustConnection):
        self.connection = connection
        self.channel: AbstractChannel | None = None
        self.exchanges: dict[str, AbstractExchange] = {}

    async def publish(self, row: Row) -> None:
        if self.channel is None:
            self.channel = await self.connection.channel(publisher_confirms=True)
        if row.exchange not in self.exchanges:
            self.exchanges[row.exchange] = await self.channel.get_exchange(row.exchange, ensure=True)
        confirmation = await self.exchanges[row.exchange].publish(
            aio_pika.Message(
                json.dumps(row.payload).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                type=row.message_type,
                message_id=str(row.message_id),
                # RabbitMQ refuses the publish unless this matches the login, so the receiver can trust it
                user_id=self.connection.url.user,
                app_id="order-service",
                timestamp=row.created_at,
            ),
            routing_key=row.routing_key,
            # Without a queue bound for it, RabbitMQ would drop the message; this way it comes back instead
            mandatory=True,
        )
        # Only an Ack means the broker has it; a Return (unroutable) or Nack means try again later
        if not isinstance(confirmation, Basic.Ack):
            raise RuntimeError(f"RabbitMQ did not accept the message ({type(confirmation).__name__})")


async def publish_pending(engine: AsyncEngine, publisher: Publisher, *, batch_size: int = 100) -> tuple[int, bool]:
    """Publishes unpublished messages, oldest first. Returns (how many were published, whether one failed)."""
    async with engine.begin() as conn:
        # SKIP LOCKED: with several order-worker copies, each relay takes different rows
        rows = (
            await conn.execute(
                select(outbox)
                .where(outbox.c.published_at.is_(None))
                .order_by(outbox.c.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        published = 0
        for row in rows:
            try:
                await publisher.publish(row)
            except Exception as exc:
                await conn.execute(
                    update(outbox)
                    .where(outbox.c.id == row.id)
                    .values(attempts=outbox.c.attempts + 1, last_error=f"{type(exc).__name__}: {exc}"[:500])
                )
                log.warning("Could not publish %s %s yet (%s); will retry", row.message_type, row.message_id, type(exc).__name__)
                # Stop here and keep the order; the rows published so far are committed below
                return published, True
            await conn.execute(
                update(outbox)
                .where(outbox.c.id == row.id)
                .values(published_at=func.now(), attempts=outbox.c.attempts + 1, last_error=None)
            )
            log.info("Published %s %s %s", row.message_type, row.message_id, json.dumps(row.payload))
            published += 1
    return published, False


class OutboxRelay:
    """Runs in order-worker, publishing the outbox every poll_seconds."""

    def __init__(self, engine: AsyncEngine, publisher: Publisher, poll_seconds: float = 1.0):
        self.engine = engine
        self.publisher = publisher
        self.poll_seconds = poll_seconds

    async def run(self) -> None:
        delay = self.poll_seconds
        while True:
            try:
                published, failed = await publish_pending(self.engine, self.publisher)
            except Exception as exc:
                # e.g. the database is restarting; the API can't write errands then either, so just wait
                log.warning("Outbox relay could not read the outbox (%s)", type(exc).__name__)
                published, failed = 0, True
            if failed:
                delay = min(delay * 2, 30)
            else:
                delay = self.poll_seconds
                if published:
                    continue  # a full batch may mean more are waiting
            await asyncio.sleep(delay)
