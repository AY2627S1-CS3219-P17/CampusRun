# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for the delivery location endpoints, ported from
#        supplier-service/tests/test_delivery_locations.py and extended with personal locations, ownership,
#        predefined-only admin edits and the rule that a location can't change while a courier is on the way.
# Author review: <to be completed by author>

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.tables import errands
from tests.conftest import auth

pytestmark = pytest.mark.anyio

ADMIN = auth(user_id=100, role="admin")
ALICE = auth(user_id=1)
BOB = auth(user_id=2)
BODY = {"name": "COM3", "description": "Meet at the level 1 main entrance.", "latitude": 1.29494, "longitude": 103.77438}


async def create(client: AsyncClient, headers: dict, **overrides) -> dict:
    response = await client.post("/delivery-locations", headers=headers, json=BODY | overrides)
    assert response.status_code == 201, response.text
    return response.json()


async def names(client: AsyncClient, headers: dict, query: str = "") -> list[str]:
    response = await client.get(f"/delivery-locations{query}", headers=headers)
    assert response.status_code == 200
    return [d["name"] for d in response.json()["items"]]


async def test_admin_creates_reads_updates_and_deactivates_a_predefined_location(client: AsyncClient) -> None:
    created = await create(client, ADMIN, predefined=True)
    assert created["predefined"] is True and created["createdBy"] == 100
    url = f"/delivery-locations/{created['id']}"

    assert await names(client, ALICE, "?q=level%201") == ["COM3"]

    edited = await client.patch(url, headers=ADMIN, json={"description": "Outside the lift lobby.", "floor": "1"})
    assert edited.status_code == 200
    assert (edited.json()["description"], edited.json()["floor"]) == ("Outside the lift lobby.", "1")

    await client.patch(url, headers=ADMIN, json={"active": False})
    assert await names(client, ALICE) == []
    assert await names(client, ALICE, "?active=false") == ["COM3"]


async def test_a_student_adds_their_own_location_that_only_they_can_see(client: AsyncClient) -> None:
    mine = await create(client, ALICE, name="My hall", floor="12", description=None)
    assert mine["predefined"] is False and mine["createdBy"] == 1 and mine["description"] is None

    assert await names(client, ALICE) == ["My hall"]
    assert await names(client, BOB) == []
    # The same 404 as a missing id, so other students' locations stay private
    assert (await client.get(f"/delivery-locations/{mine['id']}", headers=BOB)).status_code == 404
    assert (await client.patch(f"/delivery-locations/{mine['id']}", headers=BOB, json={"name": "x"})).status_code == 404
    # Admins manage the shared list, not students' own locations
    assert (await client.get(f"/delivery-locations/{mine['id']}", headers=ADMIN)).status_code == 404

    edited = await client.patch(f"/delivery-locations/{mine['id']}", headers=ALICE, json={"floor": None})
    assert edited.status_code == 200 and edited.json()["floor"] is None


async def test_the_list_can_be_narrowed_to_predefined_or_own(client: AsyncClient) -> None:
    await create(client, ADMIN, predefined=True)
    await create(client, ALICE, name="My hall")

    assert await names(client, ALICE) == ["COM3", "My hall"]
    assert await names(client, ALICE, "?predefined=true") == ["COM3"]
    assert await names(client, ALICE, "?predefined=false") == ["My hall"]


async def test_only_admins_add_or_change_predefined_locations(client: AsyncClient) -> None:
    response = await client.post("/delivery-locations", headers=ALICE, json=BODY | {"predefined": True})
    assert response.status_code == 403

    shared = await create(client, ADMIN, predefined=True)
    response = await client.patch(f"/delivery-locations/{shared['id']}", headers=ALICE, json={"name": "x"})
    assert response.status_code == 403


async def test_only_predefined_names_must_be_unique(client: AsyncClient) -> None:
    await create(client, ADMIN, predefined=True)
    duplicate = await client.post("/delivery-locations", headers=ADMIN, json=BODY | {"name": "com3", "predefined": True})
    assert duplicate.status_code == 409

    # Personal locations may share a name with each other and with a predefined one
    await create(client, ALICE)
    await create(client, ALICE)
    await create(client, BOB)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"latitude": 1.4}, "latitude"),
        ({"longitude": 103.9}, "longitude"),
        ({"name": "  "}, "name"),
        ({"floor": "x" * 11}, "floor"),
        ({"description": "x" * 301}, "description"),
        ({"colour": "red"}, "colour"),
    ],
    ids=["outside-latitude", "outside-longitude", "blank-name", "long-floor", "long-description", "unknown-field"],
)
async def test_invalid_locations_are_rejected(client: AsyncClient, overrides: dict, field: str) -> None:
    response = await client.post("/delivery-locations", headers=ALICE, json=BODY | overrides)
    assert response.status_code == 422
    assert field in response.json()["errors"]


async def test_an_update_must_change_something_and_cannot_clear_the_name(client: AsyncClient) -> None:
    mine = await create(client, ALICE)
    url = f"/delivery-locations/{mine['id']}"
    assert (await client.patch(url, headers=ALICE, json={})).status_code == 422
    assert (await client.patch(url, headers=ALICE, json={"name": None})).status_code == 422


async def add_errand(engine: AsyncEngine, location_id: int, state: str) -> None:
    courier = None if state in ("OPEN", "CANCELLED") else 2
    async with engine.begin() as conn:
        await conn.execute(
            insert(errands).values(
                requester_id=1,
                courier_id=courier,
                state=state,
                credit_status="HELD",
                title="Collect printed notes",
                reward=10,
                supplier_id=1,
                delivery_location_id=location_id,
                deliver_by=datetime.now(UTC) + timedelta(hours=1),
                cancel_reason="REQUESTER" if state == "CANCELLED" else None,
            )
        )


@pytest.mark.parametrize("state", ["ACCEPTED", "PICKED_UP", "DELIVERED"])
async def test_a_location_cannot_change_while_a_courier_is_on_the_way(
    client: AsyncClient, engine: AsyncEngine, state: str
) -> None:
    mine = await create(client, ALICE)
    await add_errand(engine, mine["id"], state)

    response = await client.patch(f"/delivery-locations/{mine['id']}", headers=ALICE, json={"floor": "2"})
    assert response.status_code == 409
    assert "courier is on the way" in response.json()["detail"]


@pytest.mark.parametrize("state", ["OPEN", "COMPLETED", "CANCELLED", "EXPIRED"])
async def test_a_location_can_change_when_no_courier_is_on_the_way(
    client: AsyncClient, engine: AsyncEngine, state: str
) -> None:
    mine = await create(client, ALICE)
    await add_errand(engine, mine["id"], state)

    response = await client.patch(f"/delivery-locations/{mine['id']}", headers=ALICE, json={"floor": "2"})
    assert response.status_code == 200


async def test_requires_sign_in(client: AsyncClient) -> None:
    assert (await client.get("/delivery-locations")).status_code == 401
