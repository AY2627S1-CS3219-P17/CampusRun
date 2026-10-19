# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for order-worker's reply consumer: replies from the wrong sender, of the wrong type or
#        with a bad body are dropped; a valid one is acknowledged only after its transaction commits; database
#        errors keep it unacknowledged and retried; repeated unexpected errors drop it.
# Author review: <to be completed by author>

import asyncio
import json

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service import worker
from order_service.worker import process
from tests.factories import add_errand, add_location, errand_row

pytestmark = pytest.mark.anyio


class FakeMessage:
    """An incoming RabbitMQ message. ack() reads the errand, to show what was committed by then."""

    def __init__(self, engine: AsyncEngine, errand_id: int, *, user_id="credit-service", type_="ReservationResult", body=None):
        self.engine = engine
        self.errand_id = errand_id
        self.user_id = user_id
        self.type = type_
        self.message_id = "reply-1"
        self.correlation_id = "command-1"
        self.body = (
            body
            if body is not None
            else json.dumps(
                {
                    "errandId": errand_id,
                    "status": "HELD",
                    "amount": 10,
                    "revision": 0,
                    "courierId": None,
                    "reason": None,
                    "rejection": None,
                }
            ).encode()
        )
        self.acked_with: list[str] = []
        self.rejected: list[bool] = []

    async def ack(self) -> None:
        self.acked_with.append((await errand_row(self.engine, self.errand_id)).credit_status)

    async def reject(self, requeue: bool = False) -> None:
        self.rejected.append(requeue)


@pytest.fixture
async def errand_id(engine: AsyncEngine) -> int:
    return await add_errand(engine, await add_location(engine), credit_status="PENDING")


async def test_a_valid_reply_is_acknowledged_after_it_is_committed(engine: AsyncEngine, errand_id: int) -> None:
    message = FakeMessage(engine, errand_id)

    await process(message, engine)

    # ack() already saw the applied reply, so the transaction had committed
    assert message.acked_with == ["HELD"]
    assert message.rejected == []


@pytest.mark.parametrize(
    "fields",
    [
        {"user_id": "order-service"},
        {"user_id": None},
        {"type_": "ReserveCredits"},
        {"body": b"{not json"},
        {"body": json.dumps({"errandId": 1}).encode()},
    ],
    ids=["another login", "no sender", "wrong type", "not JSON", "missing fields"],
)
async def test_an_invalid_reply_is_dropped_without_changing_anything(
    engine: AsyncEngine, errand_id: int, fields: dict
) -> None:
    message = FakeMessage(engine, errand_id, **fields)

    await process(message, engine)

    assert message.rejected == [False]
    assert message.acked_with == []
    assert (await errand_row(engine, errand_id)).credit_status == "PENDING"


def database_down() -> OperationalError:
    return OperationalError("UPDATE errands ...", {}, ConnectionRefusedError("database is down"))


async def test_a_database_error_keeps_the_reply_unacknowledged_and_retries(
    engine: AsyncEngine, errand_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = worker.apply_reply
    calls = 0

    async def flaky(conn, reply):
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise database_down()
        return await real(conn, reply)

    monkeypatch.setattr(worker, "apply_reply", flaky)
    message = FakeMessage(engine, errand_id)

    await process(message, engine, retry_delay=0.01)

    assert calls == 3
    assert message.acked_with == ["HELD"]
    assert message.rejected == []


async def test_a_reply_is_held_while_the_database_stays_down(
    engine: AsyncEngine, errand_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def down(conn, reply):
        raise database_down()

    monkeypatch.setattr(worker, "apply_reply", down)
    message = FakeMessage(engine, errand_id)

    task = asyncio.create_task(process(message, engine, retry_delay=0.01))
    await asyncio.sleep(0.2)
    # Still retrying: neither acknowledged nor dropped, so a restart would get it again
    assert not task.done()
    assert (message.acked_with, message.rejected) == ([], [])
    task.cancel()


async def test_a_reply_that_keeps_failing_unexpectedly_is_dropped(
    engine: AsyncEngine, errand_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def broken(conn, reply):
        nonlocal calls
        calls += 1
        raise RuntimeError("bug")

    monkeypatch.setattr(worker, "apply_reply", broken)
    message = FakeMessage(engine, errand_id)

    await process(message, engine, retry_delay=0.01)

    assert calls == worker.MAX_UNEXPECTED_FAILURES
    assert (message.acked_with, message.rejected) == ([], [False])
