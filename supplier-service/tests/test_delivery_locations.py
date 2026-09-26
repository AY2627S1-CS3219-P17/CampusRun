# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-assisted review for tests for delivery location CRUD and rules.
# Author review: <to be completed by author>

import pytest

from .conftest import ADMIN, STUDENT

pytestmark = pytest.mark.anyio

BODY = {"name": "COM3", "description": "Meet at the level 1 main entrance.", "latitude": 1.29494, "longitude": 103.77438}


async def test_crud_flow(client):
    created = await client.post("/delivery-locations", headers=ADMIN, json=BODY)
    assert created.status_code == 201
    url = f"/delivery-locations/{created.json()['id']}"

    listing = (await client.get("/delivery-locations?q=level%201", headers=STUDENT)).json()
    assert [d["name"] for d in listing["items"]] == ["COM3"]

    edited = await client.patch(url, headers=ADMIN, json={"description": "Outside the lift lobby."})
    assert edited.json()["description"] == "Outside the lift lobby."

    await client.patch(url, headers=ADMIN, json={"active": False})
    assert (await client.get("/delivery-locations", headers=STUDENT)).json()["total"] == 0
    assert (await client.get("/delivery-locations?active=false", headers=STUDENT)).status_code == 403
    assert (await client.get("/delivery-locations?active=false", headers=ADMIN)).json()["total"] == 1

    assert (await client.delete(url, headers=ADMIN)).status_code == 204
    assert (await client.get(url, headers=ADMIN)).status_code == 404


async def test_rules(client):
    await client.post("/delivery-locations", headers=ADMIN, json=BODY)
    assert (await client.post("/delivery-locations", headers=ADMIN, json=BODY | {"name": "com3"})).status_code == 409
    assert (await client.post("/delivery-locations", headers=ADMIN, json=BODY | {"latitude": 1.4})).status_code == 422
    assert (await client.post("/delivery-locations", headers=STUDENT, json=BODY)).status_code == 403
