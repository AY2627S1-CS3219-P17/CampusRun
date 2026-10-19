# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated tests for the transactional outbox, ported from user-service/tests/test_outbox.py: enqueueing
#        credit commands, the relay's ordering and retries, two relays at once, and the publisher's AMQP properties.
# Author review: <to be completed by author>

import asyncio
import json
from types import SimpleNamespace

import pytest
from pamqp.commands import Basic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.outbox import RabbitPublisher, enqueue, publish_pending
from order_service.tables import outbox

pytestmark = pytest.mark.anyio


class FakePublisher:
    def __init__(self, fail_on: set[int] | None = None):
        self.sent: list[dict] = []
        self.fail_on = fail_on or set()

    async def publish(self, row) -> None:
        if row.payload["errandId"] in self.fail_on:
            raise ConnectionError("broker down")
        await asyncio.sleep(0.01)  # let concurrent relays interleave
        self.sent.append(row.payload)


async def outbox_rows(engine: AsyncEngine) -> list:
    async with engine.connect() as conn:
        return list(await conn.execute(select(outbox).order_by(outbox.c.id)))


async def reserve(engine: AsyncEngine, *errand_ids: int) -> None:
    async with engine.begin() as conn:
        for errand_id in errand_ids:
            await enqueue(conn, "ReserveCredits", {"errandId": errand_id, "requesterId": 1, "amount": 10})


async def test_enqueue_writes_the_command_with_its_routing_key(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await enqueue(conn, "ReleaseCredits", {"errandId": 4, "requesterId": 1, "reason": "CANCELLED"})

    [row] = await outbox_rows(engine)
    assert (row.exchange, row.routing_key, row.message_type) == ("credit.commands", "reservation.release", "ReleaseCredits")
    assert row.payload == {"errandId": 4, "requesterId": 1, "reason": "CANCELLED"}
    assert row.published_at is None
    assert len(row.message_id) == 36


async def test_enqueue_refuses_an_unknown_command(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        with pytest.raises(ValueError):
            await enqueue(conn, "OpenWallet", {"userId": 1})


async def test_a_rolled_back_change_sends_nothing(engine: AsyncEngine) -> None:
    with pytest.raises(RuntimeError):
        async with engine.begin() as conn:
            await enqueue(conn, "ReserveCredits", {"errandId": 1, "requesterId": 1, "amount": 10})
            raise RuntimeError("the errand insert failed")
    assert await outbox_rows(engine) == []


async def test_relay_publishes_in_order_and_marks_each_message(engine: AsyncEngine) -> None:
    await reserve(engine, 1, 2, 3)
    publisher = FakePublisher()

    assert await publish_pending(engine, publisher) == (3, False)
    assert [p["errandId"] for p in publisher.sent] == [1, 2, 3]
    assert all(r.published_at is not None and r.attempts == 1 for r in await outbox_rows(engine))
    # Nothing left to send
    assert await publish_pending(engine, publisher) == (0, False)


async def test_relay_keeps_a_failed_message_for_later(engine: AsyncEngine) -> None:
    await reserve(engine, 1, 2, 3)

    assert await publish_pending(engine, FakePublisher(fail_on={2})) == (1, True)
    first, second, third = await outbox_rows(engine)
    assert first.published_at is not None
    assert second.published_at is None and second.attempts == 1 and "broker down" in second.last_error
    # Stops at the failure, so messages keep their order
    assert third.published_at is None and third.attempts == 0

    later = FakePublisher()
    assert await publish_pending(engine, later) == (2, False)
    assert [p["errandId"] for p in later.sent] == [2, 3]


async def test_two_relays_never_send_the_same_message(engine: AsyncEngine) -> None:
    await reserve(engine, *range(1, 21))
    one, two = FakePublisher(), FakePublisher()
    await asyncio.gather(publish_pending(engine, one, batch_size=5), publish_pending(engine, two, batch_size=5))
    sent = [p["errandId"] for p in one.sent + two.sent]
    assert len(sent) == len(set(sent)) == 10


class FakeExchange:
    def __init__(self, confirmation):
        self.confirmation = confirmation
        self.published: list[tuple] = []

    async def publish(self, message, routing_key, mandatory):
        self.published.append((message, routing_key, mandatory))
        return self.confirmation


def publisher_with(exchange: FakeExchange) -> RabbitPublisher:
    connection = SimpleNamespace(url=SimpleNamespace(user="order-service"))
    publisher = RabbitPublisher(connection)  # pyright: ignore[reportArgumentType]
    publisher.channel = object()  # pyright: ignore[reportAttributeAccessIssue]
    publisher.exchanges["credit.commands"] = exchange  # pyright: ignore[reportArgumentType]
    return publisher


async def test_publisher_sets_the_envelope_the_credit_service_checks(engine: AsyncEngine) -> None:
    await reserve(engine, 7)
    [row] = await outbox_rows(engine)
    exchange = FakeExchange(Basic.Ack())

    await publisher_with(exchange).publish(row)

    [(message, routing_key, mandatory)] = exchange.published
    assert routing_key == "reservation.reserve" and mandatory is True
    assert message.type == "ReserveCredits"
    assert message.message_id == row.message_id
    assert message.user_id == "order-service"
    assert message.delivery_mode == 2  # persistent
    assert json.loads(message.body) == {"errandId": 7, "requesterId": 1, "amount": 10}


@pytest.mark.parametrize(
    "confirmation", [Basic.Nack(), Basic.Return(reply_code=312, reply_text="NO_ROUTE")], ids=["nack", "return"]
)
async def test_publisher_treats_anything_but_an_ack_as_a_failure(engine: AsyncEngine, confirmation) -> None:
    await reserve(engine, 7)
    [row] = await outbox_rows(engine)
    with pytest.raises(RuntimeError, match="did not accept"):
        await publisher_with(FakeExchange(confirmation)).publish(row)
