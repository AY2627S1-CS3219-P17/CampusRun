# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
# Scope: AI-generated tests for the PATCH /users/me endpoint (username and password changes), including the web
#        client's username and password rules.
# Author review: <to be completed by author>

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.security import password_hash
from user_service.tables import admins, users

pytestmark = pytest.mark.anyio

ALICE = {"email": "alice@u.nus.edu", "username": "alice", "password": "S3cret-pass"}
BOB = {"email": "bob@u.nus.edu", "username": "bob", "password": "B0b-password"}


async def login(client: AsyncClient, username: str, password: str, path: str = "/auth/login"):
    return await client.post(path, data={"username": username, "password": password})


async def register_and_login(client: AsyncClient, account: dict) -> dict[str, str]:
    assert (await client.post("/auth/register", json=account)).status_code == 201
    token = (await login(client, account["username"], account["password"])).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def alice(client: AsyncClient) -> dict[str, str]:
    return await register_and_login(client, ALICE)


async def test_changes_username(client: AsyncClient, alice: dict) -> None:
    response = await client.patch("/users/me", headers=alice, json={"username": "  alice_2  "})

    assert response.status_code == 200
    assert response.json()["username"] == "alice_2"
    assert (await client.get("/users/me", headers=alice)).json()["username"] == "alice_2"
    assert (await login(client, "alice_2", ALICE["password"])).status_code == 200


async def test_can_change_case_of_own_username(client: AsyncClient, alice: dict) -> None:
    response = await client.patch("/users/me", headers=alice, json={"username": "Alice"})

    assert response.status_code == 200
    assert response.json()["username"] == "Alice"


@pytest.mark.parametrize("taken", ["bob", "BOB"])
async def test_rejects_username_taken_by_someone_else(client: AsyncClient, alice: dict, taken: str) -> None:
    await register_and_login(client, BOB)

    response = await client.patch("/users/me", headers=alice, json={"username": taken})

    assert response.status_code == 409
    assert response.json()["detail"] == "Username is already in use"
    assert (await client.get("/users/me", headers=alice)).json()["username"] == "alice"


@pytest.mark.parametrize("username", ["ab", "has space", "a@b", "has.dot", "x" * 33, None])
async def test_rejects_invalid_username(client: AsyncClient, alice: dict, username: str | None) -> None:
    response = await client.patch("/users/me", headers=alice, json={"username": username})

    assert response.status_code == 422


async def test_changes_password(client: AsyncClient, alice: dict) -> None:
    response = await client.patch(
        "/users/me",
        headers=alice,
        json={"current_password": ALICE["password"], "new_password": "Brand-new-pass1"},
    )

    assert response.status_code == 200
    assert (await login(client, "alice", ALICE["password"])).status_code == 401
    assert (await login(client, "alice", "Brand-new-pass1")).status_code == 200


async def test_changes_username_and_password_together(client: AsyncClient, alice: dict) -> None:
    response = await client.patch(
        "/users/me",
        headers=alice,
        json={"username": "alice_2", "current_password": ALICE["password"], "new_password": "Brand-new-pass1"},
    )

    assert response.status_code == 200
    assert (await login(client, "alice_2", "Brand-new-pass1")).status_code == 200


@pytest.mark.parametrize("current_password", ["wrong-password", "x" * 10_000])
async def test_wrong_current_password_changes_nothing(
    client: AsyncClient, alice: dict, current_password: str
) -> None:
    response = await client.patch(
        "/users/me",
        headers=alice,
        json={"username": "alice_2", "current_password": current_password, "new_password": "Brand-new-pass1"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Current password is incorrect"
    assert (await client.get("/users/me", headers=alice)).json()["username"] == "alice"
    assert (await login(client, "alice", ALICE["password"])).status_code == 200


async def test_new_password_requires_current_password(client: AsyncClient, alice: dict) -> None:
    response = await client.patch("/users/me", headers=alice, json={"new_password": "Brand-new-pass1"})

    assert response.status_code == 422


async def test_new_password_must_differ_from_current(client: AsyncClient, alice: dict) -> None:
    response = await client.patch(
        "/users/me",
        headers=alice,
        json={"current_password": ALICE["password"], "new_password": ALICE["password"]},
    )

    assert response.status_code == 422
    assert "must be different" in response.text


@pytest.mark.parametrize("new_password", ["Sh0rt-", "no-upper-1", "NO-LOWER-1", "No-digits-here", "NoSpecial123"])
async def test_rejects_weak_new_password(client: AsyncClient, alice: dict, new_password: str) -> None:
    response = await client.patch(
        "/users/me", headers=alice, json={"current_password": ALICE["password"], "new_password": new_password}
    )

    assert response.status_code == 422


async def test_empty_body_changes_nothing(client: AsyncClient, alice: dict) -> None:
    response = await client.patch("/users/me", headers=alice, json={})

    assert response.status_code == 200
    assert response.json()["username"] == "alice"


async def test_requires_token(client: AsyncClient) -> None:
    assert (await client.patch("/users/me", json={"username": "alice_2"})).status_code == 401


async def test_rejects_admin_token(client: AsyncClient, engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(insert(admins).values(username="root", password_hash=password_hash.hash("admin-pass")))
    token = (await login(client, "root", "admin-pass", "/auth/admin/login")).json()["access_token"]

    response = await client.patch("/users/me", headers={"Authorization": f"Bearer {token}"}, json={"username": "x_y"})

    assert response.status_code == 403


async def test_rejects_token_of_deleted_account(client: AsyncClient, engine: AsyncEngine, alice: dict) -> None:
    async with engine.begin() as conn:
        await conn.execute(delete(users))

    assert (await client.patch("/users/me", headers=alice, json={"username": "alice_2"})).status_code == 401
    assert (await client.patch("/users/me", headers=alice, json={})).status_code == 401
