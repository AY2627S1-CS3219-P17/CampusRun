# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for the errand transitions: the full lifecycle and its credit commands, every refused
#        move (wrong state, wrong party, past the deadline), the D3 races (couriers accepting at once, accept vs
#        cancel, double completion), the grace period, the supplier check on accept, edits and reward changes, and
#        the lock that keeps a delivery location from changing under an accept.
# Author review: <to be completed by author>

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.tables import delivery_locations, errands
from tests.conftest import auth
from tests.factories import ALICE, BOB, CAROL, add_errand, add_location, count, errand_row, outbox_rows
from tests.fakes import FakeServices

pytestmark = pytest.mark.anyio

ADMIN_ID = 100
ADMIN = auth(user_id=ADMIN_ID, role="admin")


@pytest.fixture
async def location(engine: AsyncEngine) -> int:
    return await add_location(engine)


async def act(client: AsyncClient, errand_id: int, action: str, user_id: int, headers: dict | None = None):
    return await client.post(f"/{errand_id}/{action}", headers=headers or auth(user_id))


def ago(**delta) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


# ---------------------------------------------------------------- lifecycle


async def test_the_full_lifecycle_and_its_credit_commands(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location)

    accepted = await act(client, errand_id, "accept", BOB)
    assert accepted.status_code == 200
    assert (accepted.json()["state"], accepted.json()["courierId"], accepted.json()["courierName"]) == ("ACCEPTED", BOB, "user2")
    assert (await act(client, errand_id, "pickup", BOB)).json()["state"] == "PICKED_UP"
    assert (await act(client, errand_id, "deliver", BOB)).json()["state"] == "DELIVERED"
    # Accepting, picking up and delivering move no credits
    assert await outbox_rows(engine) == []

    completed = (await act(client, errand_id, "complete", ALICE)).json()
    # The courier is paid by the Credit Service; until its reply arrives, the credits are PENDING
    assert (completed["state"], completed["creditStatus"]) == ("COMPLETED", "PENDING")
    row = await errand_row(engine, errand_id)
    assert all((row.accepted_at, row.picked_up_at, row.delivered_at, row.completed_at))
    [command] = await outbox_rows(engine)
    assert (command.message_type, command.payload) == (
        "TransferCredits",
        {"errandId": errand_id, "requesterId": ALICE, "courierId": BOB},
    )


@pytest.mark.parametrize("credit_status", ["HELD", "PENDING"])
async def test_the_requester_cancels_an_open_errand_and_gets_the_credits_back(
    client: AsyncClient, engine: AsyncEngine, location: int, credit_status: str
) -> None:
    # Also while the credits are still being reserved: the release follows the reserve in order
    errand_id = await add_errand(engine, location, credit_status=credit_status)

    response = await act(client, errand_id, "cancel", ALICE)

    assert response.status_code == 200
    assert (response.json()["state"], response.json()["cancelReason"], response.json()["creditStatus"]) == (
        "CANCELLED",
        "REQUESTER",
        "PENDING",
    )
    [command] = await outbox_rows(engine)
    assert (command.message_type, command.payload) == (
        "ReleaseCredits",
        {"errandId": errand_id, "requesterId": ALICE, "reason": "CANCELLED"},
    )


# ------------------------------------------------------------ refused moves


def errand_in(state: str) -> dict:
    """Column values for an errand Alice asked for, in `state`, with Bob as courier once accepted."""
    values: dict = {"state": state}
    if state not in ("OPEN", "CANCELLED"):
        values["courier_id"] = BOB
    if state == "CANCELLED":
        values["cancel_reason"] = "REQUESTER"
    if state == "COMPLETED":
        values["credit_status"] = "TRANSFERRED"
    return values


ACTIONS = {"accept": ("OPEN", CAROL), "pickup": ("ACCEPTED", BOB), "deliver": ("PICKED_UP", BOB), "complete": ("DELIVERED", ALICE), "cancel": ("OPEN", ALICE)}
STATES = ["OPEN", "ACCEPTED", "PICKED_UP", "DELIVERED", "COMPLETED", "CANCELLED", "EXPIRED"]


@pytest.mark.parametrize(
    ("action", "state"),
    [(action, state) for action, (allowed, _) in ACTIONS.items() for state in STATES if state != allowed],
)
async def test_every_other_move_is_refused_with_409(
    client: AsyncClient, engine: AsyncEngine, location: int, action: str, state: str
) -> None:
    errand_id = await add_errand(engine, location, **errand_in(state))
    _, user_id = ACTIONS[action]
    expected = 409
    if action in ("pickup", "deliver") and state in ("OPEN", "CANCELLED"):
        # There's no courier yet, so Bob isn't its courier: 403 while it's open to him, "not found" once cancelled
        expected = 403 if state == "OPEN" else 404

    response = await act(client, errand_id, action, user_id)

    assert response.status_code == expected, response.text
    assert await outbox_rows(engine) == []
    assert (await errand_row(engine, errand_id)).state == state


@pytest.mark.parametrize(
    ("action", "state", "message"),
    [
        ("accept", "ACCEPTED", None),
        ("deliver", "ACCEPTED", "This errand isn't ready to deliver yet."),
        ("complete", "PICKED_UP", "This errand isn't ready to complete yet."),
        ("complete", "COMPLETED", "This errand has already been completed."),
        ("cancel", "ACCEPTED", "This errand has already been accepted."),
        ("pickup", "EXPIRED", "This errand has expired."),
    ],
)
async def test_refusals_say_why(
    client: AsyncClient, engine: AsyncEngine, location: int, action: str, state: str, message: str | None
) -> None:
    errand_id = await add_errand(engine, location, **errand_in(state))
    # Bob is the courier of an ACCEPTED errand, so another courier's accept is the interesting case
    user_id = BOB if action in ("accept", "pickup", "deliver") else ALICE
    if action == "accept":
        user_id, message = BOB, "This errand has already been accepted."
    response = await act(client, errand_id, action, user_id)
    assert response.json()["detail"] == message


@pytest.mark.parametrize(
    ("action", "state", "user_id", "status_code", "message"),
    [
        ("accept", "OPEN", ALICE, 403, "You can't accept your own errand."),
        ("cancel", "OPEN", BOB, 403, "Only the requester can cancel an errand."),
        ("cancel", "OPEN", ADMIN_ID, 403, "Only the requester can cancel an errand."),
        ("complete", "DELIVERED", BOB, 403, "Only the requester can confirm an errand is complete."),
        ("pickup", "ACCEPTED", ALICE, 403, "Only the errand's courier can do this."),
        # Carol isn't a party to an accepted errand, so for her it doesn't exist
        ("pickup", "ACCEPTED", CAROL, 404, "This errand does not exist."),
        ("deliver", "PICKED_UP", CAROL, 404, "This errand does not exist."),
    ],
)
async def test_the_wrong_party_is_refused(
    client: AsyncClient, engine: AsyncEngine, location: int, action, state, user_id, status_code, message
) -> None:
    errand_id = await add_errand(engine, location, **errand_in(state))
    headers = ADMIN if user_id == ADMIN_ID else auth(user_id)

    response = await act(client, errand_id, action, user_id, headers)

    assert (response.status_code, response.json()["detail"]) == (status_code, message)
    assert (await errand_row(engine, errand_id)).state == state


async def test_an_errand_that_doesnt_exist_is_404(client: AsyncClient) -> None:
    assert (await act(client, 999999, "accept", BOB)).status_code == 404


async def test_an_errand_waiting_for_its_credits_cant_be_accepted(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, credit_status="PENDING")
    # Not open to couriers yet, so it doesn't exist for them
    assert (await act(client, errand_id, "accept", BOB)).status_code == 404


# ---------------------------------------------------------------- deadlines


@pytest.mark.parametrize(
    ("action", "state", "user_id"),
    [
        ("accept", "OPEN", BOB),
        ("pickup", "ACCEPTED", BOB),
        ("deliver", "PICKED_UP", BOB),
        ("cancel", "OPEN", ALICE),
    ],
)
async def test_everything_but_confirming_stops_at_the_deadline(
    client: AsyncClient, engine: AsyncEngine, location: int, action: str, state: str, user_id: int
) -> None:
    # Two minutes past the deadline: inside the grace period, which is only for confirming
    errand_id = await add_errand(engine, location, deliver_by=ago(minutes=2), **errand_in(state))

    response = await act(client, errand_id, action, user_id)

    assert (response.status_code, response.json()["detail"]) == (409, "This errand's deadline has passed.")
    assert (await errand_row(engine, errand_id)).state == state
    assert await outbox_rows(engine) == []


async def test_the_requester_can_still_confirm_during_the_grace_period(
    client: AsyncClient, engine: AsyncEngine, location: int
) -> None:
    # Delivered just before the deadline; the requester confirms two minutes after it
    errand_id = await add_errand(engine, location, deliver_by=ago(minutes=2), **errand_in("DELIVERED"))
    response = await act(client, errand_id, "complete", ALICE)
    assert (response.status_code, response.json()["state"]) == (200, "COMPLETED")


async def test_confirming_stops_when_the_grace_period_ends_even_before_the_sweeper_runs(
    client: AsyncClient, engine: AsyncEngine, location: int
) -> None:
    errand_id = await add_errand(engine, location, deliver_by=ago(minutes=6), **errand_in("DELIVERED"))

    response = await act(client, errand_id, "complete", ALICE)

    assert (response.status_code, response.json()["detail"]) == (409, "This errand's deadline has passed.")
    assert await outbox_rows(engine) == []


# -------------------------------------------------------------------- races


async def test_only_one_of_many_couriers_accepting_at_once_wins(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location)
    couriers = list(range(10, 20))

    responses = await asyncio.gather(*(act(client, errand_id, "accept", c) for c in couriers))

    winners = [c for c, r in zip(couriers, responses) if r.status_code == 200]
    assert len(winners) == 1
    assert sorted(r.status_code for r in responses) == [200] + [409] * 9
    assert all(r.json()["detail"] == "This errand has already been accepted." for r in responses if r.status_code == 409)
    assert (await errand_row(engine, errand_id)).courier_id == winners[0]


async def test_accept_and_cancel_at_once_have_one_winner(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    for _ in range(5):
        errand_id = await add_errand(engine, location)
        accept, cancel = await asyncio.gather(act(client, errand_id, "accept", BOB), act(client, errand_id, "cancel", ALICE))

        assert sorted((accept.status_code, cancel.status_code)) == [200, 409]
        row = await errand_row(engine, errand_id)
        commands = [r for r in await outbox_rows(engine) if r.payload["errandId"] == errand_id]
        if cancel.status_code == 200:
            assert row.state == "CANCELLED" and [c.message_type for c in commands] == ["ReleaseCredits"]
        else:
            assert row.state == "ACCEPTED" and commands == []


async def test_completing_twice_pays_once(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, **errand_in("DELIVERED"))

    first, second = await asyncio.gather(act(client, errand_id, "complete", ALICE), act(client, errand_id, "complete", ALICE))

    assert sorted((first.status_code, second.status_code)) == [200, 409]
    assert [r.message_type for r in await outbox_rows(engine)] == ["TransferCredits"]
    # And once more, afterwards
    again = await act(client, errand_id, "complete", ALICE)
    assert (again.status_code, again.json()["detail"]) == (409, "This errand has already been completed.")


async def test_accept_waits_for_a_delivery_location_edit_in_progress(
    client: AsyncClient, engine: AsyncEngine, location: int
) -> None:
    errand_id = await add_errand(engine, location)
    async with engine.begin() as conn:
        # A location edit holds this lock while it checks whether a courier is on the way
        await conn.execute(
            select(delivery_locations.c.id).where(delivery_locations.c.id == location).with_for_update()
        )
        accepting = asyncio.create_task(act(client, errand_id, "accept", BOB))
        await asyncio.sleep(0.5)
        assert not accepting.done()
    # Once the edit commits, the accept goes ahead
    assert (await accepting).status_code == 200


# --------------------------------------------------------- supplier check (D13)


async def test_an_errand_whose_supplier_was_deactivated_cant_be_accepted(
    client: AsyncClient, engine: AsyncEngine, location: int
) -> None:
    errand_id = await add_errand(engine, location, supplier_id=3)  # deactivated in the fake Supplier Service

    response = await act(client, errand_id, "accept", BOB)

    assert (response.status_code, response.json()["detail"]) == (409, "This supplier is no longer available.")
    assert (await errand_row(engine, errand_id)).state == "OPEN"
    # The requester can still cancel it
    assert (await act(client, errand_id, "cancel", ALICE)).status_code == 200


async def test_accept_goes_ahead_if_suppliers_cant_be_checked(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices, location: int
) -> None:
    errand_id = await add_errand(engine, location)
    services.down.add("suppliers")
    response = await act(client, errand_id, "accept", BOB)
    assert response.status_code == 200 and response.json()["supplier"] is None


# --------------------------------------------------------------------- edit


async def edit(client: AsyncClient, errand_id: int, user_id: int = ALICE, **changes):
    return await client.patch(f"/{errand_id}", headers=auth(user_id), json=changes)


async def test_edit_changes_only_the_fields_sent(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location)

    response = await edit(client, errand_id, title="Collect lecture notes", supplierId=2)

    assert response.status_code == 200
    body = response.json()
    assert (body["title"], body["supplierId"], body["supplier"]["name"], body["credits"]) == (
        "Collect lecture notes",
        2,
        "Printer @ Com 2",
        10,
    )
    # No reward change, so no credit command, and still open to couriers
    assert body["creditStatus"] == "HELD" and await outbox_rows(engine) == []


async def test_a_new_reward_is_re_reserved_with_a_rising_revision(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location)

    first = (await edit(client, errand_id, credits=15)).json()
    # Hidden from couriers until the Credit Service confirms the new amount
    assert (first["credits"], first["creditStatus"]) == (15, "PENDING")
    assert (await act(client, errand_id, "accept", BOB)).status_code == 404

    # As if the Credit Service's reply had arrived (Task 8)
    async with engine.begin() as conn:
        await conn.execute(errands.update().where(errands.c.id == errand_id).values(credit_status="HELD"))
    await edit(client, errand_id, credits=12)

    commands = await outbox_rows(engine)
    assert [(c.message_type, c.payload["amount"], c.payload["revision"]) for c in commands] == [
        ("AdjustReservation", 15, 1),
        ("AdjustReservation", 12, 2),
    ]
    assert commands[0].payload == {"errandId": errand_id, "requesterId": ALICE, "amount": 15, "revision": 1}


async def test_the_same_reward_sends_no_command(client: AsyncClient, engine: AsyncEngine, location: int) -> None:
    errand_id = await add_errand(engine, location, reward=10)
    response = await edit(client, errand_id, credits=10, title="Same reward")
    assert response.json()["creditStatus"] == "HELD" and await outbox_rows(engine) == []


async def test_a_new_delivery_point_becomes_the_requesters_own_location(
    client: AsyncClient, engine: AsyncEngine, location: int
) -> None:
    errand_id = await add_errand(engine, location)
    response = await edit(client, errand_id, building="My hall", latitude=1.3, longitude=103.775)
    assert response.json()["deliveryLocation"]["name"] == "My hall"
    assert await count(engine, delivery_locations) == 2


@pytest.mark.parametrize(
    ("values", "user_id", "status_code", "message"),
    [
        (errand_in("ACCEPTED"), ALICE, 409, "This errand has already been accepted."),
        ({"credit_status": "PENDING"}, ALICE, 409, "This errand's credits are still being reserved. Try again in a moment."),
        ({"deliver_by": datetime.now(UTC) - timedelta(minutes=1)}, ALICE, 409, "This errand's deadline has passed."),
        ({}, BOB, 403, "Only the requester can change an errand."),
    ],
    ids=["accepted", "credits-pending", "past-deadline", "not-the-requester"],
)
async def test_edit_is_refused_once_its_not_the_requesters_open_errand(
    client: AsyncClient, engine: AsyncEngine, location: int, values: dict, user_id: int, status_code: int, message: str
) -> None:
    errand_id = await add_errand(engine, location, **values)
    response = await edit(client, errand_id, user_id, title="Changed")
    assert (response.status_code, response.json()["detail"]) == (status_code, message)
    assert (await errand_row(engine, errand_id)).title == "Collect printed notes"


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({}, "form"),
        ({"title": None}, "title"),
        ({"credits": 101}, "credits"),
        ({"supplierId": 3}, "supplierId"),
        ({"floor": "2"}, "building"),
    ],
    ids=["nothing", "clear-title", "too-many-credits", "deactivated-supplier", "partial-new-point"],
)
async def test_invalid_edits_are_rejected(
    client: AsyncClient, engine: AsyncEngine, location: int, changes: dict, field: str
) -> None:
    errand_id = await add_errand(engine, location)
    response = await edit(client, errand_id, **changes)
    assert response.status_code == 422
    assert field in response.json()["errors"]


async def test_an_edit_cant_move_the_deadline_past_24_hours_after_posting(
    client: AsyncClient, engine: AsyncEngine, location: int
) -> None:
    errand_id = await add_errand(engine, location)
    async with engine.begin() as conn:
        await conn.execute(errands.update().where(errands.c.id == errand_id).values(created_at=ago(hours=20)))

    later = (datetime.now(UTC) + timedelta(hours=6)).isoformat()
    response = await edit(client, errand_id, deliverBy=later)
    assert response.json()["errors"] == {"deliverBy": "Choose a time within 24 hours of when you posted the errand."}


async def test_raising_the_reward_checks_the_extra_credits(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices, location: int
) -> None:
    errand_id = await add_errand(engine, location, reward=10)
    services.wallets[ALICE] = {"status": "ACTIVE", "available": 3}

    assert (await edit(client, errand_id, credits=13)).status_code == 200
    async with engine.begin() as conn:
        await conn.execute(errands.update().where(errands.c.id == errand_id).values(credit_status="HELD"))
    response = await edit(client, errand_id, credits=17)
    assert response.json()["errors"] == {"credits": "You have 3 credits available."}
