# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review for tests for the worker: sender and body checks, dead-lettering, replies and retries.
# Author review: <to be completed by author>

import json

import pytest
from sqlalchemy.exc import OperationalError

from credit_service import worker
from credit_service.config import get_settings

from .conftest import FakeExchange, FakeMessage

pytestmark = pytest.mark.anyio


def message(type_, body, *, sender, routing_key=None, **kwargs) -> FakeMessage:
    keys = {
        "OpenWallet": "wallet.open",
        "ReserveCredits": "reservation.reserve",
        "AdjustReservation": "reservation.adjust",
        "TransferCredits": "reservation.transfer",
        "ReleaseCredits": "reservation.release",
    }
    return FakeMessage(
        type=type_,
        body=json.dumps(body).encode(),
        user_id=sender,
        routing_key=routing_key or keys.get(type_, "wallet.open"),
        **kwargs,
    )


async def handle(engine, msg: FakeMessage) -> FakeExchange:
    replies = FakeExchange()
    await worker.process(msg, engine, replies, "credit-service", get_settings())
    return replies


async def wallet(client, user_id):
    from .conftest import auth

    return (await client.get("/wallets/me", headers=auth(user_id))).json()


async def test_open_wallet_from_the_user_service(engine, client):
    msg = message("OpenWallet", {"userId": 5}, sender="user-service")
    replies = await handle(engine, msg)
    assert msg.outcome == "ack"
    assert replies.published == []  # OpenWallet has no reply
    assert (await wallet(client, 5))["available"] == 100


async def test_reserve_replies_to_the_sender_and_acknowledges(engine):
    await handle(engine, message("OpenWallet", {"userId": 5}, sender="user-service"))
    msg = message("ReserveCredits", {"errandId": 1, "requesterId": 5, "amount": 15}, sender="order-service")
    replies = await handle(engine, msg)
    assert msg.outcome == "ack"
    [(routing_key, reply)] = replies.published
    assert routing_key == "order-service"
    assert reply.correlation_id == msg.message_id
    assert reply.type == "ReservationResult"
    assert reply.user_id == "credit-service"
    assert json.loads(reply.body) == {
        "errandId": 1,
        "status": "HELD",
        "amount": 15,
        "revision": 0,
        "courierId": None,
        "reason": None,
        "rejection": None,
    }


async def test_a_redelivered_command_changes_nothing_but_is_answered_again(engine, client):
    await handle(engine, message("OpenWallet", {"userId": 5}, sender="user-service"))
    body = {"errandId": 1, "requesterId": 5, "amount": 15}
    first = await handle(engine, message("ReserveCredits", body, sender="order-service"))
    again = await handle(engine, message("ReserveCredits", body, sender="order-service"))
    assert first.published[0][1].body == again.published[0][1].body
    assert (await wallet(client, 5))["available"] == 85


@pytest.mark.parametrize(
    "msg, problem",
    [
        (message("ReserveCredits", {"errandId": 1, "requesterId": 5, "amount": 15}, sender="user-service"), "may not be sent"),
        (message("OpenWallet", {"userId": 5}, sender="order-service"), "may not be sent"),
        (message("OpenWallet", {"userId": 5}, sender=None), "may not be sent"),
        (message("DeleteWallet", {"userId": 5}, sender="user-service"), "unknown command"),
        (message("OpenWallet", {"userId": 5}, sender="user-service", routing_key="reservation.reserve"), "routing key"),
        (message("OpenWallet", {"userId": -1}, sender="user-service"), "invalid body"),
        (message("OpenWallet", {"userId": 5, "credits": 1000}, sender="user-service"), "invalid body"),
        (message("ReserveCredits", {"errandId": 1, "requesterId": 5, "amount": 0}, sender="order-service"), "invalid body"),
        (message("TransferCredits", {"errandId": 1, "requesterId": 5, "courierId": 5}, sender="order-service"), "invalid body"),
        (message("OpenWallet", {"userId": 5}, sender="user-service", message_id=None), "message_id"),
    ],
)
async def test_invalid_messages_are_dead_lettered_without_touching_wallets(engine, client, msg, problem, caplog):
    replies = await handle(engine, msg)
    assert msg.outcome == "dead-letter"
    assert replies.published == []
    assert problem in caplog.text
    assert (await wallet(client, 5))["status"] == "PENDING"


async def test_a_body_that_is_not_json_is_dead_lettered(engine):
    msg = FakeMessage(type="OpenWallet", body=b"not json", user_id="user-service", routing_key="wallet.open")
    await handle(engine, msg)
    assert msg.outcome == "dead-letter"


async def test_a_command_contradicting_the_data_is_dead_lettered(engine):
    await handle(engine, message("OpenWallet", {"userId": 5}, sender="user-service"))
    await handle(engine, message("ReserveCredits", {"errandId": 1, "requesterId": 5, "amount": 15}, sender="order-service"))
    msg = message("ReleaseCredits", {"errandId": 1, "requesterId": 6, "reason": "CANCELLED"}, sender="order-service")
    replies = await handle(engine, msg)
    assert msg.outcome == "dead-letter"
    assert replies.published == []


async def test_a_database_outage_is_retried_until_it_clears(engine, monkeypatch, client):
    monkeypatch.setattr(worker.asyncio, "sleep", _no_sleep)
    real_apply = worker.ledger.apply
    failures = iter([True, True, True, True, False])

    async def flaky_apply(*args, **kwargs):
        if next(failures):
            raise OperationalError("SELECT 1", {}, ConnectionRefusedError("database is down"))
        return await real_apply(*args, **kwargs)

    monkeypatch.setattr(worker.ledger, "apply", flaky_apply)
    msg = message("OpenWallet", {"userId": 5}, sender="user-service")
    await handle(engine, msg)
    # Four outages in a row: more than the limit for unexpected errors, but these are expected to clear
    assert msg.outcome == "ack"
    assert (await wallet(client, 5))["available"] == 100


async def test_an_unexpected_error_is_dead_lettered_after_a_few_tries(engine, monkeypatch):
    monkeypatch.setattr(worker.asyncio, "sleep", _no_sleep)
    calls = 0

    async def broken_apply(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise ZeroDivisionError("bug")

    monkeypatch.setattr(worker.ledger, "apply", broken_apply)
    msg = message("OpenWallet", {"userId": 5}, sender="user-service")
    await handle(engine, msg)
    assert msg.outcome == "dead-letter"
    assert calls == worker.MAX_UNEXPECTED_FAILURES


def test_transient_errors_are_recognised():
    class Orig(Exception):
        sqlstate = "40P01"

    from sqlalchemy.exc import DBAPIError, IntegrityError

    assert worker.is_transient(OperationalError("x", {}, Exception()))
    assert worker.is_transient(ConnectionRefusedError())
    assert worker.is_transient(DBAPIError("x", {}, Orig()))
    assert not worker.is_transient(IntegrityError("x", {}, Exception()))
    assert not worker.is_transient(ValueError())


async def _no_sleep(_seconds):
    return None
