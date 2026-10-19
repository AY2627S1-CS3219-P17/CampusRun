# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for the sweeper: which errands expire and when, two sweepers at once, the reconciler's
#        threshold and the command it resends for each state, expiresAt in responses, and GET /admin/stuck.
# Author review: <to be completed by author>

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.outbox import enqueue
from order_service.sweeper import expire_due, reconcile
from order_service.tables import outbox
from tests.conftest import auth
from tests.factories import ALICE, BOB, add_errand, add_location, errand_row, outbox_rows

pytestmark = pytest.mark.anyio

ADMIN = auth(user_id=100, role="admin")


@pytest.fixture
async def location(engine: AsyncEngine) -> int:
    return await add_location(engine)


def ago(**delta) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


def ahead(**delta) -> datetime:
    return datetime.now(UTC) + timedelta(**delta)


# ------------------------------------------------------------------ expiry


@pytest.mark.parametrize(
    ("state", "extra"), [("OPEN", {}), ("ACCEPTED", {"courier_id": BOB}), ("PICKED_UP", {"courier_id": BOB})]
)
async def test_an_errand_not_yet_delivered_expires_at_the_deadline(
    engine: AsyncEngine, location: int, state: str, extra: dict
) -> None:
    late = await add_errand(engine, location, state=state, deliver_by=ago(seconds=1), **extra)
    on_time = await add_errand(engine, location, state=state, deliver_by=ahead(minutes=1), **extra)

    assert await expire_due(engine) == 1

    row = await errand_row(engine, late)
    assert (row.state, row.credit_status) == ("EXPIRED", "PENDING")
    assert row.expired_at is not None
    assert (await errand_row(engine, on_time)).state == state
    [command] = await outbox_rows(engine)
    assert command.message_type == "ReleaseCredits"
    assert command.payload == {"errandId": late, "requesterId": ALICE, "reason": "EXPIRED"}


async def test_a_delivered_errand_expires_only_after_the_grace_period(engine: AsyncEngine, location: int) -> None:
    in_grace = await add_errand(engine, location, state="DELIVERED", courier_id=BOB, deliver_by=ago(minutes=2))
    past_grace = await add_errand(engine, location, state="DELIVERED", courier_id=BOB, deliver_by=ago(minutes=6))

    assert await expire_due(engine) == 1

    assert (await errand_row(engine, in_grace)).state == "DELIVERED"
    assert (await errand_row(engine, past_grace)).state == "EXPIRED"


@pytest.mark.parametrize(
    ("state", "extra"),
    [("COMPLETED", {"courier_id": BOB}), ("CANCELLED", {"cancel_reason": "REQUESTER"}), ("EXPIRED", {})],
)
async def test_an_ended_errand_is_untouched(engine: AsyncEngine, location: int, state: str, extra: dict) -> None:
    errand_id = await add_errand(engine, location, state=state, deliver_by=ago(hours=1), **extra)

    assert await expire_due(engine) == 0

    assert (await errand_row(engine, errand_id)).state == state
    assert await outbox_rows(engine) == []


async def test_two_sweepers_at_once_expire_each_errand_once(engine: AsyncEngine, location: int) -> None:
    ids = [await add_errand(engine, location, deliver_by=ago(minutes=1)) for _ in range(6)]

    counts = await asyncio.gather(expire_due(engine, batch_size=2), expire_due(engine, batch_size=2))

    assert sum(counts) == 6
    commands = await outbox_rows(engine)
    assert sorted(c.payload["errandId"] for c in commands) == ids
    assert {c.message_type for c in commands} == {"ReleaseCredits"}


async def test_expires_at_adds_the_grace_period_only_once_delivered(
    client: AsyncClient, engine: AsyncEngine, location: int
) -> None:
    deadline = ahead(hours=1)
    delivered = {"courier_id": BOB, "delivered_at": ago(minutes=1), "deliver_by": deadline}
    open_id = await add_errand(engine, location, deliver_by=deadline)
    delivered_id = await add_errand(engine, location, state="DELIVERED", **delivered)
    # Confirmed during the grace period: expiresAt still includes it, so it isn't earlier than completedAt
    completed_id = await add_errand(engine, location, state="COMPLETED", completed_at=ago(seconds=1), **delivered)

    def grace(errand: dict) -> timedelta:
        return datetime.fromisoformat(errand["expiresAt"]) - datetime.fromisoformat(errand["deliverBy"])

    assert grace((await client.get(f"/{open_id}", headers=auth(ALICE))).json()) == timedelta(0)
    assert grace((await client.get(f"/{delivered_id}", headers=auth(ALICE))).json()) == timedelta(minutes=5)
    assert grace((await client.get(f"/{completed_id}", headers=auth(ALICE))).json()) == timedelta(minutes=5)


# -------------------------------------------------------------- reconcile


@pytest.mark.parametrize(
    ("values", "command", "payload"),
    [
        ({}, "ReserveCredits", {"amount": 10}),
        ({"reward": 15, "reward_revision": 2}, "AdjustReservation", {"amount": 15, "revision": 2}),
        ({"state": "COMPLETED", "courier_id": BOB}, "TransferCredits", {"courierId": BOB}),
        ({"state": "CANCELLED", "cancel_reason": "REQUESTER"}, "ReleaseCredits", {"reason": "CANCELLED"}),
        ({"state": "EXPIRED"}, "ReleaseCredits", {"reason": "EXPIRED"}),
    ],
)
async def test_reconcile_resends_the_command_for_where_the_credits_should_end_up(
    engine: AsyncEngine, location: int, values: dict, command: str, payload: dict
) -> None:
    errand_id = await add_errand(engine, location, credit_status="PENDING", updated_at=ago(minutes=6), **values)

    assert await reconcile(engine) == 1

    [row] = await outbox_rows(engine)
    assert row.message_type == command
    assert row.payload == {"errandId": errand_id, "requesterId": ALICE} | payload


async def test_reconcile_waits_for_the_threshold_and_then_restarts_it(engine: AsyncEngine, location: int) -> None:
    await add_errand(engine, location, credit_status="PENDING", updated_at=ago(minutes=4))
    await add_errand(engine, location, credit_status="HELD", updated_at=ago(hours=1))
    assert await reconcile(engine) == 0

    stuck_id = await add_errand(engine, location, credit_status="PENDING", updated_at=ago(minutes=6))
    assert await reconcile(engine) == 1
    # Sent again only after another full wait
    assert await reconcile(engine) == 0
    assert [c.payload["errandId"] for c in await outbox_rows(engine)] == [stuck_id]


async def test_reconcile_skips_an_errand_whose_command_is_still_in_the_outbox(engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, credit_status="PENDING", updated_at=ago(minutes=6))
    async with engine.begin() as conn:
        await enqueue(conn, "ReserveCredits", {"errandId": errand_id, "requesterId": ALICE, "amount": 10})

    assert await reconcile(engine) == 0

    async with engine.begin() as conn:
        await conn.execute(update(outbox).values(published_at=ago(minutes=6)))
    assert await reconcile(engine) == 1


async def test_two_reconcilers_at_once_resend_each_command_once(engine: AsyncEngine, location: int) -> None:
    for _ in range(5):
        await add_errand(engine, location, credit_status="PENDING", updated_at=ago(minutes=6))

    counts = await asyncio.gather(reconcile(engine, batch_size=2), reconcile(engine, batch_size=2))

    assert sum(counts) == 5
    assert len(await outbox_rows(engine)) == 5


# ------------------------------------------------------------ admin view


async def test_admins_see_errands_whose_credits_are_stuck(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    stuck_id = await add_errand(engine, location, credit_status="PENDING", updated_at=ago(minutes=6))
    await add_errand(engine, location, credit_status="PENDING")

    response = await client.get("/admin/stuck", headers=ADMIN)

    assert response.status_code == 200
    assert [e["id"] for e in response.json()["items"]] == [stuck_id]
    assert (await client.get("/admin/stuck", headers=auth(ALICE))).status_code == 403
