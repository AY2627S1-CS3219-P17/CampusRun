# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for applying the Credit Service's replies: each target reached, duplicate and late
#        replies, a refused reserve cancelling the errand, cancel racing the reserve, refused and stale reward
#        changes, and replies that must be ignored.
# Author review: <to be completed by author>

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.credit import ReservationResult, apply_reply
from tests.conftest import auth
from tests.factories import ALICE, BOB, add_errand, add_location, errand_row

pytestmark = pytest.mark.anyio


@pytest.fixture
async def location(engine: AsyncEngine) -> int:
    return await add_location(engine)


def reply(errand_id: int, status: str | None, **fields) -> ReservationResult:
    """A reply as the Credit Service's worker sends it: camelCase JSON (model_dump_json(by_alias=True))."""
    body = {
        "errandId": errand_id,
        "status": status,
        "amount": 10,
        "revision": 0,
        "courierId": None,
        "reason": None,
        "rejection": None,
    } | fields
    return ReservationResult.model_validate_json(json.dumps(body))


async def apply(engine: AsyncEngine, result: ReservationResult) -> str:
    async with engine.begin() as conn:
        return await apply_reply(conn, result)


async def test_the_reply_model_reads_the_credit_services_json_and_ignores_new_fields() -> None:
    result = reply(7, "HELD", courierId=None, somethingNew=True, rejection="A_NEW_CODE")
    assert (result.errand_id, result.status, result.rejection) == (7, "HELD", "A_NEW_CODE")


# ------------------------------------------------------------- each target


async def test_a_held_reserve_makes_the_errand_visible_to_couriers(
    client: AsyncClient, engine: AsyncEngine, location: int
) -> None:
    errand_id = await add_errand(engine, location, credit_status="PENDING")
    explore = await client.get("/", headers=auth(BOB))
    assert explore.json()["items"] == []

    assert await apply(engine, reply(errand_id, "HELD")) == "applied"

    assert (await errand_row(engine, errand_id)).credit_status == "HELD"
    explore = await client.get("/", headers=auth(BOB))
    assert [e["id"] for e in explore.json()["items"]] == [errand_id]


async def test_a_held_adjustment_keeps_the_new_reward(engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, credit_status="PENDING", reward=15, reward_revision=1)

    assert await apply(engine, reply(errand_id, "HELD", amount=15, revision=1)) == "applied"

    row = await errand_row(engine, errand_id)
    assert (row.credit_status, row.reward, row.credit_rejection) == ("HELD", 15, None)


async def test_a_transfer_pays_a_completed_errand(engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, state="COMPLETED", courier_id=BOB, credit_status="PENDING")

    assert await apply(engine, reply(errand_id, "TRANSFERRED", courierId=BOB)) == "applied"

    assert (await errand_row(engine, errand_id)).credit_status == "TRANSFERRED"


@pytest.mark.parametrize(("state", "extra"), [("CANCELLED", {"cancel_reason": "REQUESTER"}), ("EXPIRED", {})])
async def test_a_release_returns_the_credits_of_an_ended_errand(
    engine: AsyncEngine, location: int, state: str, extra: dict
) -> None:
    errand_id = await add_errand(engine, location, state=state, credit_status="PENDING", **extra)

    assert await apply(engine, reply(errand_id, "RELEASED", reason=state if state == "EXPIRED" else "CANCELLED")) == "applied"

    row = await errand_row(engine, errand_id)
    assert (row.state, row.credit_status) == (state, "RELEASED")


# ------------------------------------------------------- duplicates and order


async def test_a_duplicate_reply_changes_nothing(engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, credit_status="PENDING")
    assert await apply(engine, reply(errand_id, "HELD")) == "applied"
    before = await errand_row(engine, errand_id)

    assert await apply(engine, reply(errand_id, "HELD")) == "ignored"

    assert await errand_row(engine, errand_id) == before


async def test_a_late_held_reply_after_the_transfer_leaves_it_transferred(engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, state="COMPLETED", courier_id=BOB, credit_status="PENDING")
    assert await apply(engine, reply(errand_id, "TRANSFERRED", courierId=BOB)) == "applied"

    assert await apply(engine, reply(errand_id, "HELD")) == "ignored"

    assert (await errand_row(engine, errand_id)).credit_status == "TRANSFERRED"


async def test_a_held_reply_after_a_cancel_waits_for_the_release(engine: AsyncEngine, location: int) -> None:
    # Cancelled before the reserve's reply arrived: the reserve held the credits, then the release returns them
    errand_id = await add_errand(
        engine, location, state="CANCELLED", cancel_reason="REQUESTER", credit_status="PENDING"
    )

    assert await apply(engine, reply(errand_id, "HELD")) == "ignored"
    assert (await errand_row(engine, errand_id)).credit_status == "PENDING"

    assert await apply(engine, reply(errand_id, "RELEASED", reason="CANCELLED")) == "applied"
    assert (await errand_row(engine, errand_id)).credit_status == "RELEASED"


async def test_a_release_that_overtook_its_reserve_leaves_the_reward_alone(engine: AsyncEngine, location: int) -> None:
    # The Credit Service's placeholder for a release that arrived first has amount 0
    errand_id = await add_errand(
        engine, location, state="CANCELLED", cancel_reason="REQUESTER", credit_status="PENDING"
    )

    reply_ = reply(errand_id, "REJECTED", amount=0, reason="CANCELLED_BEFORE_RESERVE")
    assert await apply(engine, reply_) == "applied"

    row = await errand_row(engine, errand_id)
    assert (row.credit_status, row.reward, row.cancel_reason) == ("REJECTED", 10, "REQUESTER")


async def test_a_reply_to_an_older_reward_change_is_ignored(engine: AsyncEngine, location: int) -> None:
    # The reward was changed (revision 1) after the reserve was held, and the reserve's reply comes again
    errand_id = await add_errand(engine, location, credit_status="PENDING", reward=15, reward_revision=1)

    assert await apply(engine, reply(errand_id, "HELD", amount=10, revision=0)) == "ignored"

    row = await errand_row(engine, errand_id)
    assert (row.credit_status, row.reward) == ("PENDING", 15)


# ---------------------------------------------------------------- refusals


@pytest.mark.parametrize("reason", ["INSUFFICIENT_CREDITS", "NO_WALLET"])
async def test_a_refused_reserve_cancels_the_errand(
    client: AsyncClient, engine: AsyncEngine, location: int, reason: str
) -> None:
    errand_id = await add_errand(engine, location, credit_status="PENDING")

    assert await apply(engine, reply(errand_id, "REJECTED", reason=reason, rejection=reason)) == "cancelled"

    row = await errand_row(engine, errand_id)
    assert (row.state, row.cancel_reason, row.credit_status, row.credit_rejection) == (
        "CANCELLED",
        reason,
        "REJECTED",
        reason,
    )
    assert row.cancelled_at is not None
    explore = await client.get("/", headers=auth(BOB))
    assert explore.json()["items"] == []
    mine = await client.get("/me/requests", params={"tab": "inactive"}, headers=auth(ALICE))
    assert [e["cancelReason"] for e in mine.json()["items"]] == [reason]


async def test_a_refused_reserve_after_a_cancel_keeps_the_requesters_cancel(engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(
        engine, location, state="CANCELLED", cancel_reason="REQUESTER", credit_status="PENDING"
    )

    refused = reply(errand_id, "REJECTED", reason="INSUFFICIENT_CREDITS", rejection="INSUFFICIENT_CREDITS")
    assert await apply(engine, refused) == "applied"
    # The release's reply describes the same rejected reservation, without a rejection of its own
    assert await apply(engine, reply(errand_id, "REJECTED", reason="INSUFFICIENT_CREDITS")) == "ignored"

    row = await errand_row(engine, errand_id)
    assert (row.state, row.cancel_reason, row.credit_status, row.credit_rejection) == (
        "CANCELLED",
        "REQUESTER",
        "REJECTED",
        "INSUFFICIENT_CREDITS",
    )


async def test_a_refused_reward_change_puts_the_old_reward_back(engine: AsyncEngine, location: int) -> None:
    # The requester raised the reward from 10 to 50 (revision 1), but only 10 could be held
    errand_id = await add_errand(engine, location, credit_status="PENDING", reward=50, reward_revision=1)

    refused = reply(errand_id, "HELD", amount=10, revision=1, rejection="INSUFFICIENT_CREDITS")
    assert await apply(engine, refused) == "applied"
    row = await errand_row(engine, errand_id)
    assert (row.state, row.credit_status, row.reward, row.credit_rejection) == (
        "OPEN",
        "HELD",
        10,
        "INSUFFICIENT_CREDITS",
    )

    assert await apply(engine, refused) == "ignored"
    assert await errand_row(engine, errand_id) == row


async def test_a_transfer_the_courier_has_no_wallet_for_stays_pending(engine: AsyncEngine, location: int) -> None:
    # The credits stay held, so the reconciler can send the transfer again (Task 9)
    errand_id = await add_errand(engine, location, state="COMPLETED", courier_id=BOB, credit_status="PENDING")

    assert await apply(engine, reply(errand_id, "HELD", rejection="NO_COURIER_WALLET")) == "ignored"

    assert (await errand_row(engine, errand_id)).credit_status == "PENDING"


async def test_a_transfer_to_another_courier_is_ignored(engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, state="COMPLETED", courier_id=BOB, credit_status="PENDING")

    assert await apply(engine, reply(errand_id, "TRANSFERRED", courierId=99)) == "ignored"

    assert (await errand_row(engine, errand_id)).credit_status == "PENDING"


# ------------------------------------------------------- replies to ignore


async def test_a_reply_without_a_reservation_is_ignored(engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, state="COMPLETED", courier_id=BOB, credit_status="PENDING")
    before = await errand_row(engine, errand_id)

    assert await apply(engine, reply(errand_id, None, amount=0, rejection="NO_RESERVATION")) == "ignored"

    assert await errand_row(engine, errand_id) == before


async def test_a_reply_for_an_unknown_errand_is_ignored(engine: AsyncEngine) -> None:
    assert await apply(engine, reply(12345, "HELD")) == "ignored"
