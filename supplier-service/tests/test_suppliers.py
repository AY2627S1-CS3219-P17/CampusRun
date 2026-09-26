# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-assisted review for tests for supplier CRUD, validation, search, filters, sorting, paging and distance.
# Author review: <to be completed by author>

from datetime import time

import pytest
from alembic import command
from sqlalchemy import select, text

from supplier_service.routes.suppliers import is_open, open_now_condition
from supplier_service.tables import suppliers

from .conftest import ADMIN, ALEMBIC_CONFIG, STUDENT, supplier_body

pytestmark = pytest.mark.anyio


async def create(client, **overrides) -> dict:
    response = await client.post("/suppliers", headers=ADMIN, json=supplier_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------ create


async def test_create_returns_supplier_in_web_client_shape(client):
    response = await client.post("/suppliers", headers=ADMIN, json=supplier_body())
    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"/suppliers/{body['id']}"
    assert isinstance(body["id"], int)
    # The fields frontend/src/types/supplier.ts already uses
    assert body["name"] == "Test Kiosk"
    assert body["type"] == "Food"
    assert body["location"] == "COM3, Floor 1"
    assert body["startTime"] == "08:00"
    assert body["endTime"] == "20:00"
    assert body["active"] is True
    # and the extra ones the service adds
    assert body["locationDescription"] == "Next to the lift lobby"
    assert {"latitude", "longitude", "isOpenNow", "createdAt", "updatedAt"} <= body.keys()


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"name": "   "}, "name"),
        ({"name": "x" * 101}, "name"),
        ({"type": "Weapons"}, "type"),
        ({"latitude": 1.35}, "latitude"),  # outside NUS
        ({"longitude": 103.7526298}, "longitude"),
        ({"startTime": "25:00"}, "startTime"),
        ({"endTime": None}, "endTime"),
        ({"imageUrl": "javascript:alert(1)"}, "imageUrl"),
        ({"surprise": 1}, "surprise"),
    ],
)
async def test_create_rejects_invalid_input(client, overrides, field):
    response = await client.post("/suppliers", headers=ADMIN, json=supplier_body(**overrides))
    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Some details need fixing."
    assert field in body["errors"]


async def test_missing_fields_are_listed(client):
    response = await client.post("/suppliers", headers=ADMIN, json={})
    assert response.status_code == 422
    assert {"name", "type", "building", "locationDescription", "latitude", "longitude", "startTime", "endTime"} <= set(
        response.json()["errors"]
    )


async def test_duplicate_name_ignoring_case_is_409(client):
    await create(client)
    response = await client.post("/suppliers", headers=ADMIN, json=supplier_body(name="test KIOSK"))
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# -------------------------------------------------------------------- read


async def test_get_by_id_and_404(client):
    created = await create(client)
    assert (await client.get(f"/suppliers/{created['id']}", headers=STUDENT)).json()["id"] == created["id"]
    assert (await client.get("/suppliers/999999", headers=STUDENT)).status_code == 404


@pytest.mark.parametrize("bad_id", ["abc", "0"])
async def test_bad_id_is_422(client, bad_id):
    response = await client.get(f"/suppliers/{bad_id}", headers=STUDENT)
    assert response.status_code == 422
    assert response.json()["errors"]["supplier_id"] == "This id is not valid."


# ------------------------------------------------------------------ update


async def test_patch_changes_only_given_fields(client):
    created = await create(client)
    response = await client.patch(f"/suppliers/{created['id']}", headers=ADMIN, json={"name": "Renamed Kiosk", "floor": None})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed Kiosk"
    assert body["floor"] is None
    assert body["location"] == "COM3"
    assert body["building"] == "COM3"
    assert body["updatedAt"] > created["updatedAt"]


async def test_patch_rejects_clearing_required_field_and_empty_body(client):
    created = await create(client)
    url = f"/suppliers/{created['id']}"
    assert (await client.patch(url, headers=ADMIN, json={"name": None})).status_code == 422
    assert (await client.patch(url, headers=ADMIN, json={"startTime": None})).status_code == 422
    assert (await client.patch(url, headers=ADMIN, json={})).status_code == 422


async def test_patch_to_taken_name_is_409(client):
    await create(client, name="Alpha")
    beta = await create(client, name="Beta")
    response = await client.patch(f"/suppliers/{beta['id']}", headers=ADMIN, json={"name": "ALPHA"})
    assert response.status_code == 409


# --------------------------------------------------- deactivate and delete


async def test_deactivated_supplier_hidden_from_students(client):
    created = await create(client)
    await client.patch(f"/suppliers/{created['id']}", headers=ADMIN, json={"active": False})

    assert (await client.get("/suppliers", headers=STUDENT)).json()["total"] == 0
    assert (await client.get("/suppliers", headers=ADMIN)).json()["total"] == 0
    deactivated = (await client.get("/suppliers?active=false", headers=ADMIN)).json()
    assert [s["active"] for s in deactivated["items"]] == [False]
    # still readable by id, so old errands can show it
    assert (await client.get(f"/suppliers/{created['id']}", headers=STUDENT)).json()["active"] is False


async def test_student_cannot_list_deactivated(client):
    assert (await client.get("/suppliers?active=false", headers=STUDENT)).status_code == 403


async def test_reactivate(client):
    created = await create(client, active=False)
    await client.patch(f"/suppliers/{created['id']}", headers=ADMIN, json={"active": True})
    assert (await client.get("/suppliers", headers=STUDENT)).json()["total"] == 1


async def test_delete_hides_supplier_and_frees_name(client, engine):
    created = await create(client)
    url = f"/suppliers/{created['id']}"
    assert (await client.delete(url, headers=ADMIN)).status_code == 204
    assert (await client.get(url, headers=ADMIN)).status_code == 404
    assert (await client.delete(url, headers=ADMIN)).status_code == 404
    assert (await client.patch(url, headers=ADMIN, json={"name": "x"})).status_code == 404
    assert (await client.get("/suppliers?active=false", headers=ADMIN)).json()["total"] == 0
    await create(client)  # the same name is allowed again

    async with engine.connect() as conn:  # the row is kept for history
        assert await conn.scalar(text("SELECT count(*) FROM suppliers WHERE deleted_at IS NOT NULL")) == 1


# ------------------------------------------------ search, filter, sort, page


async def seed_three(client):
    await create(client, name="Cool Spot", type="Food", building="COM2", locationDescription="Opp LT16",
                 latitude=1.2940156, longitude=103.7738478)
    await create(client, name="NUS Co-op", type="Shopping", building="Central Library",
                 locationDescription="Inside the library on the right side", latitude=1.2967866, longitude=103.7732677)
    await create(client, name="Good Day Cafe", type="Drinks", building="Medicine+Science Library",
                 locationDescription="Inside MedScience library", latitude=1.2967989, longitude=103.7794336)


async def names(client, query: str, headers=STUDENT) -> list[str]:
    response = await client.get(f"/suppliers?{query}", headers=headers)
    assert response.status_code == 200, response.text
    return [s["name"] for s in response.json()["items"]]


async def test_keyword_search_ignores_case_over_name_building_and_description(client):
    await seed_three(client)
    assert await names(client, "q=cool") == ["Cool Spot"]
    assert await names(client, "q=LIBRARY") == ["Good Day Cafe", "NUS Co-op"]
    assert await names(client, "q=com2") == ["Cool Spot"]
    assert await names(client, "q=%25") == []  # a literal %, not a wildcard


async def test_filter_by_type_and_building(client):
    await seed_three(client)
    assert await names(client, "type=Food&type=Drinks") == ["Cool Spot", "Good Day Cafe"]
    assert await names(client, "building=central%20library") == ["NUS Co-op"]
    assert await names(client, "type=Food&building=Central%20Library") == []


async def test_buildings_list(client):
    await seed_three(client)
    await create(client, name="Another", building="com2")
    response = await client.get("/suppliers/buildings", headers=STUDENT)
    assert response.json() == ["Central Library", "COM2", "Medicine+Science Library"]


async def test_sorting(client):
    await seed_three(client)
    assert await names(client, "sort=name") == ["Cool Spot", "Good Day Cafe", "NUS Co-op"]
    assert await names(client, "sort=-name") == ["NUS Co-op", "Good Day Cafe", "Cool Spot"]
    assert await names(client, "sort=type") == ["Good Day Cafe", "Cool Spot", "NUS Co-op"]
    assert await names(client, "sort=-createdAt") == ["Good Day Cafe", "NUS Co-op", "Cool Spot"]


async def test_nearest_first_with_distance(client):
    await seed_three(client)
    # standing at COM3
    items = (await client.get("/suppliers?sort=distance&nearLat=1.2949&nearLng=103.7744", headers=STUDENT)).json()["items"]
    assert [s["name"] for s in items] == ["Cool Spot", "NUS Co-op", "Good Day Cafe"]
    assert 100 < items[0]["distanceM"] < 200
    assert await names(client, "nearLat=1.2949&nearLng=103.7744&radius=300") == ["Cool Spot", "NUS Co-op"]


async def test_distance_needs_a_point(client):
    response = await client.get("/suppliers?sort=distance", headers=STUDENT)
    assert response.status_code == 422
    assert "sort" in response.json()["errors"]
    assert (await client.get("/suppliers?nearLat=1.29", headers=STUDENT)).status_code == 422


async def test_pagination(client):
    for i in range(25):
        await create(client, name=f"Kiosk {i:02d}")
    first = (await client.get("/suppliers?pageSize=10", headers=STUDENT)).json()
    assert (first["total"], first["totalPages"], first["pageSize"]) == (25, 3, 10)
    assert [s["name"] for s in first["items"]][:2] == ["Kiosk 00", "Kiosk 01"]
    last = (await client.get("/suppliers?page=3&pageSize=10", headers=STUDENT)).json()
    assert len(last["items"]) == 5
    assert (await client.get("/suppliers?page=4&pageSize=10", headers=STUDENT)).json()["items"] == []
    assert (await client.get("/suppliers?pageSize=101", headers=STUDENT)).status_code == 422


async def test_open_now_filter(client):
    await create(client, name="Always", startTime="00:00", endTime="23:59")
    assert "Always" in await names(client, "openNow=true")


@pytest.mark.parametrize(
    "now, start, end, expected",
    [
        (time(12, 0), time(9, 0), time(18, 0), True),
        (time(8, 59), time(9, 0), time(18, 0), False),
        (time(18, 0), time(9, 0), time(18, 0), True),
        (time(1, 0), time(11, 0), time(2, 0), True),  # closes after midnight
        (time(3, 0), time(11, 0), time(2, 0), False),
    ],
)
def test_is_open(now, start, end, expected):
    assert is_open(now, start, end) is expected


async def test_open_now_sql_matches_python_rule(client, engine):
    await create(client, name="Day", startTime="09:00", endTime="18:00")
    await create(client, name="Late", startTime="11:00", endTime="02:00")
    async with engine.connect() as conn:
        for now in (time(1, 0), time(10, 0), time(12, 0), time(20, 0), time(3, 0)):
            found = set((await conn.scalars(select(suppliers.c.name).where(open_now_condition(now)))).all())
            expected = {n for n, s, e in [("Day", time(9), time(18)), ("Late", time(11), time(2))] if is_open(now, s, e)}
            assert found == expected, now


async def test_keyword_search_can_use_trigram_index(client, engine):
    await seed_three(client)
    async with engine.connect() as conn:
        await conn.execute(text("SET enable_seqscan = off"))
        plan = "\n".join(
            (await conn.execute(text(
                "EXPLAIN SELECT id FROM suppliers "
                "WHERE (name || ' ' || building || ' ' || location_description) ILIKE '%library%'"
            ))).scalars()
        )
    assert "ix_suppliers_search_trgm" in plan


def test_migrations_match_tables():
    # Fails if tables.py was changed without a new Alembic migration
    command.check(ALEMBIC_CONFIG)
