# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for creating, reading and listing errands: the ReserveCredits command written with the
#        errand, delivery points, the supplier and wallet checks, validation, Explore, My Requests/My Tasks, the
#        admin view, who can see an errand, search (including supplier names), sorting, paging, and what the
#        responses show when another service is down.
# Author review: <to be completed by author>

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.config import get_settings
from order_service.tables import delivery_locations, errands, outbox
from tests.conftest import auth
from tests.factories import ALICE, BOB, CAROL, add_errand, add_location, count
from tests.fakes import FakeServices

pytestmark = pytest.mark.anyio

ADMIN = auth(user_id=100, role="admin")


def soon(**delta) -> str:
    return (datetime.now(UTC) + timedelta(**(delta or {"hours": 1}))).isoformat()


def body(**overrides) -> dict:
    values = {
        "title": "Collect printed notes",
        "supplierId": 1,
        "building": "COM3",
        "floor": "1",
        "description": "Main entrance",
        "latitude": 1.29494,
        "longitude": 103.77438,
        "deliverBy": soon(),
        "credits": 10,
    }
    return {k: v for k, v in (values | overrides).items() if v is not ...}


async def create(client: AsyncClient, user_id: int = ALICE, **overrides) -> dict:
    response = await client.post("/", headers=auth(user_id), json=body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def titles(client: AsyncClient, url: str, user_id: int = BOB) -> list[str]:
    response = await client.get(url, headers=auth(user_id))
    assert response.status_code == 200, response.text
    return [e["title"] for e in response.json()["items"]]


# ------------------------------------------------------------------- create


async def test_create_saves_the_errand_and_its_reserve_command_together(
    client: AsyncClient, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "root_path", "/api/orders")
    response = await client.post("/", headers=auth(ALICE), json=body())

    assert response.status_code == 201
    errand = response.json()
    assert response.headers["Location"] == f"/api/orders/{errand['id']}"
    # Not visible to couriers until the Credit Service has reserved the credits
    assert (errand["state"], errand["creditStatus"], errand["credits"]) == ("OPEN", "PENDING", 10)
    assert errand["requesterId"] == ALICE and errand["requesterName"] == "user1"
    assert errand["supplier"]["name"] == "Robot Cafe"
    assert errand["courierId"] is None and errand["courierName"] is None
    deliver_by = datetime.fromisoformat(errand["deliverBy"])
    # Not delivered yet, so it expires at the deadline itself (D2)
    assert datetime.fromisoformat(errand["expiresAt"]) == deliver_by

    async with engine.connect() as conn:
        [command] = (await conn.execute(select(outbox))).all()
    assert (command.message_type, command.routing_key) == ("ReserveCredits", "reservation.reserve")
    assert command.payload == {"errandId": errand["id"], "requesterId": ALICE, "amount": 10}


async def test_a_new_delivery_point_becomes_the_requesters_own_location(client: AsyncClient, engine: AsyncEngine) -> None:
    errand = await create(client, building="My hall", floor="12", description=None)

    location = errand["deliveryLocation"]
    assert (location["name"], location["floor"], location["predefined"]) == ("My hall", "12", False)
    async with engine.connect() as conn:
        owner = await conn.scalar(select(delivery_locations.c.created_by).where(delivery_locations.c.id == location["id"]))
    assert owner == ALICE
    # The requester can pick it again, and nobody else sees it in their list
    mine = await client.get("/delivery-locations?predefined=false", headers=auth(ALICE))
    assert [d["name"] for d in mine.json()["items"]] == ["My hall"]


NO_CUSTOM = {"building": ..., "floor": ..., "description": ..., "latitude": ..., "longitude": ...}


async def test_a_saved_delivery_location_can_be_chosen(client: AsyncClient, engine: AsyncEngine) -> None:
    location_id = await add_location(engine)
    errand = await create(client, deliveryLocationId=location_id, **NO_CUSTOM)
    assert errand["deliveryLocation"]["id"] == location_id
    assert await count(engine, delivery_locations) == 1


@pytest.mark.parametrize(
    "location",
    [{"predefined": False, "created_by": BOB}, {"predefined": True, "active": False}],
    ids=["someone-elses", "deactivated"],
)
async def test_an_unusable_delivery_location_is_rejected(client: AsyncClient, engine: AsyncEngine, location: dict) -> None:
    location_id = await add_location(engine, **location)
    response = await client.post("/", headers=auth(ALICE), json=body(deliveryLocationId=location_id, **NO_CUSTOM))
    assert response.status_code == 422
    assert "deliveryLocationId" in response.json()["errors"]


async def test_a_saved_and_a_new_delivery_point_together_are_rejected(client: AsyncClient, engine: AsyncEngine) -> None:
    location_id = await add_location(engine)
    response = await client.post("/", headers=auth(ALICE), json=body(deliveryLocationId=location_id))
    assert response.status_code == 422
    assert "form" in response.json()["errors"]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"building": ...}, "building"),
        ({"latitude": ...}, "latitude"),
        ({"latitude": 1.4}, "latitude"),
        ({"title": " "}, "title"),
        ({"title": "x" * 101}, "title"),
        ({"credits": 0}, "credits"),
        ({"credits": 101}, "credits"),
        ({"deliverBy": soon(minutes=10)}, "deliverBy"),
        ({"deliverBy": soon(hours=25)}, "deliverBy"),
        ({"supplierId": 0}, "supplierId"),
        ({"colour": "red"}, "colour"),
    ],
    ids=[
        "no-building",
        "no-latitude",
        "outside-area",
        "blank-title",
        "long-title",
        "credits-0",
        "credits-101",
        "too-soon",
        "too-late",
        "bad-supplier-id",
        "unknown-field",
    ],
)
async def test_invalid_requests_are_rejected_with_the_field(
    client: AsyncClient, engine: AsyncEngine, overrides: dict, field: str
) -> None:
    response = await client.post("/", headers=auth(ALICE), json=body(**overrides))
    assert response.status_code == 422
    assert field in response.json()["errors"]
    assert await count(engine, errands) == 0


async def test_a_time_without_a_zone_is_campus_time(client: AsyncClient) -> None:
    campus = datetime.now(ZoneInfo("Asia/Singapore")) + timedelta(hours=1)
    errand = await create(client, deliverBy=campus.replace(tzinfo=None, microsecond=0).isoformat())
    assert datetime.fromisoformat(errand["deliverBy"]) == campus.replace(microsecond=0)


@pytest.mark.parametrize("supplier_id", [3, 99], ids=["deactivated", "unknown"])
async def test_the_supplier_must_be_active(client: AsyncClient, engine: AsyncEngine, supplier_id: int) -> None:
    response = await client.post("/", headers=auth(ALICE), json=body(supplierId=supplier_id))
    assert response.status_code == 422
    assert response.json()["errors"] == {"supplierId": "Choose a supplier from the list."}
    assert await count(engine, errands) == 0


async def test_nothing_is_written_if_suppliers_cant_be_checked(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices
) -> None:
    services.down.add("suppliers")
    response = await client.post("/", headers=auth(ALICE), json=body())
    assert response.status_code == 503
    assert (await count(engine, errands), await count(engine, outbox), await count(engine, delivery_locations)) == (0, 0, 0)


@pytest.mark.parametrize(
    ("wallet", "message"),
    [
        ({"status": "ACTIVE", "available": 5}, "You have 5 credits available."),
        ({"status": "PENDING", "available": None}, "Your credits are still being set up. Try again in a moment."),
    ],
    ids=["too-few", "wallet-pending"],
)
async def test_the_wallet_pre_check_stops_errands_that_would_be_refused(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices, wallet: dict, message: str
) -> None:
    services.wallets[ALICE] = wallet
    response = await client.post("/", headers=auth(ALICE), json=body(credits=10))
    assert response.status_code == 422
    assert response.json()["errors"] == {"credits": message}
    assert await count(engine, errands) == 0


async def test_the_wallet_pre_check_is_skipped_if_credits_cant_be_read(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices
) -> None:
    # Advisory only: the Credit Service's reserve still decides, and refuses it if the credits aren't there
    services.down.add("credits")
    await create(client)
    assert await count(engine, outbox) == 1


async def test_creating_requires_sign_in(client: AsyncClient) -> None:
    assert (await client.post("/", json=body())).status_code == 401


# ------------------------------------------------------------------ explore


async def test_explore_shows_only_open_errands_with_reserved_credits_from_others(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    location = await add_location(engine)
    await add_errand(engine, location, title="Visible")
    await add_errand(engine, location, title="Credits pending", credit_status="PENDING")
    await add_errand(engine, location, title="Past deadline", deliver_by=datetime.now(UTC) - timedelta(minutes=1))
    await add_errand(engine, location, title="Accepted", state="ACCEPTED", courier_id=CAROL)
    await add_errand(engine, location, title="Bob's own", requester_id=BOB)

    assert await titles(client, "/", BOB) == ["Visible"]


async def test_explore_sorts(client: AsyncClient, engine: AsyncEngine) -> None:
    location = await add_location(engine)
    for title, reward in [("first", 5), ("second", 20), ("third", 10)]:
        await add_errand(engine, location, title=title, reward=reward)

    assert await titles(client, "/") == ["third", "second", "first"]
    assert await titles(client, "/?sort=least-recent") == ["first", "second", "third"]
    assert await titles(client, "/?sort=most-credits") == ["second", "third", "first"]
    assert await titles(client, "/?sort=least-credits") == ["first", "third", "second"]


async def test_explore_pages(client: AsyncClient, engine: AsyncEngine) -> None:
    location = await add_location(engine)
    for i in range(3):
        await add_errand(engine, location, title=f"errand {i}")

    first = (await client.get("/?pageSize=2", headers=auth(BOB))).json()
    second = (await client.get("/?pageSize=2&page=2", headers=auth(BOB))).json()
    assert (first["total"], first["totalPages"], len(first["items"]), len(second["items"])) == (3, 2, 2, 1)


async def test_search_matches_title_location_and_supplier_name(client: AsyncClient, engine: AsyncEngine) -> None:
    com3 = await add_location(engine, name="COM3")
    utown = await add_location(engine, name="UTown Residence")
    await add_errand(engine, com3, title="Collect notes", supplier_id=2)
    await add_errand(engine, utown, title="Bring dinner", supplier_id=1)
    await add_errand(engine, com3, title="Lunch run", supplier_id=3)  # supplier since deactivated
    await add_errand(engine, utown, title="Noodles for the study group", supplier_id=1)

    assert await titles(client, "/?q=notes") == ["Collect notes"]
    assert await titles(client, "/?q=utown") == ["Noodles for the study group", "Bring dinner"]
    assert await titles(client, "/?q=printer") == ["Collect notes"]
    # One errand matches "noodle" by its title, the other by its supplier, which was later deactivated
    assert await titles(client, "/?q=noodle") == ["Noodles for the study group", "Lunch run"]
    # The total and pages count every match, not just the first page
    response = (await client.get("/?q=noodle&pageSize=1", headers=auth(BOB))).json()
    assert (response["total"], response["totalPages"], response["supplierSearch"]) == (2, 2, True)


async def test_search_still_works_without_supplier_names_if_suppliers_are_down(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices
) -> None:
    location = await add_location(engine, name="COM3")
    await add_errand(engine, location, title="Collect notes", supplier_id=1)
    services.down.add("suppliers")

    robot = (await client.get("/?q=robot", headers=auth(BOB))).json()
    notes = (await client.get("/?q=notes", headers=auth(BOB))).json()
    assert (robot["items"], robot["supplierSearch"]) == ([], False)
    assert [e["title"] for e in notes["items"]] == ["Collect notes"]
    # The errand still shows, without its supplier details
    assert notes["items"][0]["supplier"] is None


async def test_names_are_missing_rather_than_failing_if_users_are_down(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices
) -> None:
    location = await add_location(engine)
    await add_errand(engine, location)
    services.down.add("users")

    [errand] = (await client.get("/", headers=auth(BOB))).json()["items"]
    assert errand["requesterName"] is None and errand["supplier"]["name"] == "Robot Cafe"


async def test_one_page_needs_one_call_for_suppliers_and_one_for_names(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices
) -> None:
    location = await add_location(engine)
    for supplier_id in (1, 2, 1, 2):
        await add_errand(engine, location, supplier_id=supplier_id)

    await client.get("/", headers=auth(BOB))
    assert sorted(r.url.path for r in services.requests) == ["/internal/usernames", "/lookup"]


# ---------------------------------------------------------------- one errand


async def test_who_can_see_an_accepted_errand(client: AsyncClient, engine: AsyncEngine) -> None:
    location = await add_location(engine)
    errand_id = await add_errand(engine, location, state="ACCEPTED", courier_id=BOB)

    assert (await client.get(f"/{errand_id}", headers=auth(ALICE))).status_code == 200
    courier_view = (await client.get(f"/{errand_id}", headers=auth(BOB))).json()
    assert (courier_view["courierId"], courier_view["courierName"]) == (BOB, "user2")
    assert (await client.get(f"/{errand_id}", headers=ADMIN)).status_code == 200
    # Anyone else gets the same 404 as for an id that doesn't exist
    assert (await client.get(f"/{errand_id}", headers=auth(CAROL))).status_code == 404
    assert (await client.get("/999999", headers=auth(ALICE))).status_code == 404


async def test_anyone_can_see_an_errand_in_explore(client: AsyncClient, engine: AsyncEngine) -> None:
    location = await add_location(engine, predefined=False, created_by=ALICE, name="My hall")
    errand_id = await add_errand(engine, location)

    response = await client.get(f"/{errand_id}", headers=auth(CAROL))
    assert response.status_code == 200
    # A courier deciding whether to accept sees where it goes, even though the location is Alice's own
    assert response.json()["deliveryLocation"]["name"] == "My hall"


# ----------------------------------------------------------- my errands


async def test_my_requests_and_my_tasks_by_tab(client: AsyncClient, engine: AsyncEngine) -> None:
    location = await add_location(engine)
    await add_errand(engine, location, title="open")
    await add_errand(engine, location, title="on the way", state="PICKED_UP", courier_id=BOB)
    await add_errand(engine, location, title="done", state="COMPLETED", courier_id=BOB, credit_status="TRANSFERRED")
    await add_errand(engine, location, title="cancelled", state="CANCELLED", cancel_reason="REQUESTER")
    await add_errand(engine, location, title="expired", state="EXPIRED", courier_id=BOB)
    await add_errand(engine, location, title="Bob asked", requester_id=BOB)

    assert await titles(client, "/me/requests", ALICE) == ["on the way", "open"]
    assert await titles(client, "/me/requests?tab=completed", ALICE) == ["done"]
    assert await titles(client, "/me/requests?tab=inactive", ALICE) == ["expired", "cancelled"]
    # Bob is a courier on Alice's errands and a requester on his own, at the same time
    assert await titles(client, "/me/tasks", BOB) == ["on the way"]
    assert await titles(client, "/me/tasks?tab=completed", BOB) == ["done"]
    assert await titles(client, "/me/tasks?tab=inactive", BOB) == ["expired"]
    assert await titles(client, "/me/requests", BOB) == ["Bob asked"]


async def test_my_requests_search(client: AsyncClient, engine: AsyncEngine) -> None:
    location = await add_location(engine)
    await add_errand(engine, location, title="Collect notes")
    await add_errand(engine, location, title="Bring dinner")
    assert await titles(client, "/me/requests?q=dinner", ALICE) == ["Bring dinner"]


async def test_an_unknown_tab_is_rejected(client: AsyncClient) -> None:
    assert (await client.get("/me/requests?tab=pending", headers=auth(ALICE))).status_code == 422


# -------------------------------------------------------------------- admin


async def test_admins_can_list_a_requesters_or_couriers_errands(client: AsyncClient, engine: AsyncEngine) -> None:
    location = await add_location(engine)
    await add_errand(engine, location, title="Alice's", state="ACCEPTED", courier_id=BOB)
    await add_errand(engine, location, title="Carol's", requester_id=CAROL)

    response = await client.get(f"/admin/errands?requesterId={ALICE}", headers=ADMIN)
    assert [e["title"] for e in response.json()["items"]] == ["Alice's"]
    response = await client.get(f"/admin/errands?courierId={BOB}&state=ACCEPTED", headers=ADMIN)
    assert [e["title"] for e in response.json()["items"]] == ["Alice's"]
    assert (await client.get("/admin/errands", headers=ADMIN)).json()["total"] == 2


async def test_students_cannot_use_the_admin_view(client: AsyncClient) -> None:
    assert (await client.get("/admin/errands", headers=auth(ALICE))).status_code == 403


async def test_no_database_connection_is_held_while_other_services_are_called(
    client: AsyncClient, engine: AsyncEngine, services: FakeServices
) -> None:
    location = await add_location(engine, name="COM3")
    await add_errand(engine, location)
    held: list[int] = []
    services.on_request = lambda request: held.append(engine.pool.checkedout())

    await create(client)
    await client.get("/?q=robot", headers=auth(BOB))
    await client.get("/1", headers=auth(BOB))
    await client.get("/me/requests", headers=auth(ALICE))

    # A slow Supplier, User or Credit Service never ties up the database connection pool
    assert held and set(held) == {0}
