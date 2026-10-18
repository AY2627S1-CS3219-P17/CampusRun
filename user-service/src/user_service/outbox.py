# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-generated transactional outbox: enqueueing the OpenWallet command with a registration, and the relay
#        that publishes queued messages to RabbitMQ with publisher confirms.
# Author review: <to be completed by author>

"""Messages from this service to others, sent reliably.

Publishing straight to RabbitMQ after committing a registration has a gap: if the broker is down, or the process
dies between the commit and the publish, the user exists but their wallet is never opened. Publishing before the
commit has the opposite gap: a wallet for a registration that then rolls back.

So the message is written to the outbox table in the same transaction as the user (enqueue_open_wallet), and
OutboxRelay publishes it afterwards, retrying until RabbitMQ confirms it. A message can be published more than
once (a crash after the publish but before marking it), which is fine because the credit service ignores a second
OpenWallet for the same user.
"""

import asyncio
import json
import logging
from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection
from pamqp.commands import Basic
from pydantic import SecretStr
from sqlalchemy import Row, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from user_service.tables import outbox

log = logging.getLogger(__name__)

CREDIT_COMMANDS = "credit.commands"


async def enqueue_open_wallet(conn: AsyncConnection, user_id: int) -> None:
    """Asks the credit service to open the user's wallet, once this transaction commits."""
    await conn.execute(
        insert(outbox).values(
            exchange=CREDIT_COMMANDS,
            routing_key="wallet.open",
            message_type="OpenWallet",
            payload={"userId": user_id},
        )
    )


class Publisher(Protocol):
    async def publish(self, row: Row) -> None: ...


class RabbitPublisher:
    """Publishes outbox rows to RabbitMQ, connecting on first use and reconnecting on its own after that."""

    def __init__(self, url: SecretStr):
        self.url = url
        self.connection: AbstractRobustConnection | None = None
        self.exchanges: dict[str, AbstractExchange] = {}

    async def publish(self, row: Row) -> None:
        if self.connection is None:
            self.connection = await aio_pika.connect_robust(self.url.get_secret_value(), timeout=5)
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
                app_id="user-service",
                timestamp=row.created_at,
            ),
            routing_key=row.routing_key,
            # Without a queue bound for it, RabbitMQ would drop the message; this way it comes back instead
            mandatory=True,
        )
        # Only an Ack means the broker has it; a Return (unroutable) or Nack means try again later
        if not isinstance(confirmation, Basic.Ack):
            raise RuntimeError(f"RabbitMQ did not accept the message ({type(confirmation).__name__})")

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()


async def publish_pending(engine: AsyncEngine, publisher: Publisher, *, batch_size: int = 100) -> tuple[int, bool]:
    """Publishes unpublished messages, oldest first. Returns (how many were published, whether one failed)."""
    async with engine.begin() as conn:
        # SKIP LOCKED: with several user-service instances, each relay takes different rows
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
            published += 1
    return published, False


class OutboxRelay:
    """Runs in the background of the API process, publishing the outbox every poll_seconds."""

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
                # e.g. the database is restarting; registration fails then too, so just wait
                log.warning("Outbox relay could not read the outbox (%s)", type(exc).__name__)
                published, failed = 0, True
            if failed:
                delay = min(delay * 2, 30)
            else:
                delay = self.poll_seconds
                if published:
                    continue  # a full batch may mean more are waiting
            await asyncio.sleep(delay)
