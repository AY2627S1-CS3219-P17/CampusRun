# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-generated tests for admin user management: searching users, promoting, stepping down, the last-admin
#        rule under concurrent requests, stale admin tokens, and the new role reaching the next access token.
# Author review: <to be completed by author>

import asyncio

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service import admin as admin_routes
from user_service.config import get_settings
from user_service.security import Role, create_access_token
from user_service.tables import users

pytestmark = pytest.mark.anyio


async def add_user(engine: AsyncEngine, username: str, role: Role = "student") -> int:
    async with engine.begin() as conn:
        return await conn.scalar(
            insert(users)
            .values(email=f"{username}@u.nus.edu", username=username, password_hash="x", role=role)
            .returning(users.c.id)
        )


async def role_of(engine: AsyncEngine, user_id: int) -> str:
    async with engine.connect() as conn:
        return await conn.scalar(select(users.c.role).where(users.c.id == user_id))


def bearer(user_id: int, role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role, get_settings())}"}


@pytest.fixture
async def admin_id(engine: AsyncEngine) -> int:
    return await add_user(engine, "boss", "admin")


async def test_a_student_cant_use_any_admin_route(client: AsyncClient, engine: AsyncEngine, admin_id: int) -> None:
    student = await add_user(engine, "alice")
    headers = bearer(student, "student")

    assert (await client.get("/admin/users", headers=headers)).status_code == 403
    assert (await client.post(f"/admin/users/{student}/promote", headers=headers)).status_code == 403
    assert (await client.post("/admin/me/step-down", headers=headers)).status_code == 403
    assert (await client.get("/admin/users")).status_code == 401


async def test_lists_users_by_username_with_only_the_admin_fields(
    client: AsyncClient, engine: AsyncEngine, admin_id: int
) -> None:
    alice = await add_user(engine, "alice")

    response = await client.get("/admin/users", headers=bearer(admin_id, "admin"))

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"id": alice, "username": "alice", "email": "alice@u.nus.edu", "role": "student"},
            {"id": admin_id, "username": "boss", "email": "boss@u.nus.edu", "role": "admin"},
        ],
        "total": 2,
        "page": 1,
        "page_size": 20,
        "total_pages": 1,
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("q=ALI", ["alice"]),  # username, any case
        ("q=bob@u.nus", ["bob"]),  # email
        ("q=%25", []),  # % is a literal character, not a wildcard
        ("role=admin", ["boss"]),
        ("role=student&q=b", ["bob"]),
    ],
)
async def test_searches_and_filters(
    client: AsyncClient, engine: AsyncEngine, admin_id: int, query: str, expected: list[str]
) -> None:
    await add_user(engine, "alice")
    await add_user(engine, "bob")

    response = await client.get(f"/admin/users?{query}", headers=bearer(admin_id, "admin"))

    assert response.status_code == 200
    assert [user["username"] for user in response.json()["items"]] == expected


async def test_pages_the_list(client: AsyncClient, engine: AsyncEngine, admin_id: int) -> None:
    for name in ("alice", "bob", "carol"):
        await add_user(engine, name)

    body = (await client.get("/admin/users?page=2&page_size=2", headers=bearer(admin_id, "admin"))).json()

    assert [user["username"] for user in body["items"]] == ["boss", "carol"]
    assert (body["total"], body["total_pages"]) == (4, 2)


async def test_promotes_a_student(client: AsyncClient, engine: AsyncEngine, admin_id: int) -> None:
    alice = await add_user(engine, "alice")

    response = await client.post(f"/admin/users/{alice}/promote", headers=bearer(admin_id, "admin"))

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert await role_of(engine, alice) == "admin"


async def test_promoting_an_unknown_user_is_404(client: AsyncClient, admin_id: int) -> None:
    response = await client.post("/admin/users/999999/promote", headers=bearer(admin_id, "admin"))
    assert response.status_code == 404


async def test_promoting_an_admin_is_409(client: AsyncClient, engine: AsyncEngine, admin_id: int) -> None:
    other = await add_user(engine, "deputy", "admin")
    response = await client.post(f"/admin/users/{other}/promote", headers=bearer(admin_id, "admin"))
    assert response.status_code == 409


async def test_steps_down_while_another_admin_is_left(client: AsyncClient, engine: AsyncEngine, admin_id: int) -> None:
    await add_user(engine, "deputy", "admin")

    response = await client.post("/admin/me/step-down", headers=bearer(admin_id, "admin"))

    assert response.status_code == 200
    assert response.json()["role"] == "student"
    assert await role_of(engine, admin_id) == "student"


async def test_the_last_admin_cant_step_down(client: AsyncClient, engine: AsyncEngine, admin_id: int) -> None:
    response = await client.post("/admin/me/step-down", headers=bearer(admin_id, "admin"))

    assert response.status_code == 409
    assert await role_of(engine, admin_id) == "admin"


async def test_the_last_two_admins_stepping_down_at_once_leave_one(
    client: AsyncClient, engine: AsyncEngine, admin_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    deputy = await add_user(engine, "deputy", "admin")
    count_admins = admin_routes._count_admins

    async def count_then_pause(conn) -> int:
        count = await count_admins(conn)
        # Without the lock, both requests would count two admins here, then both step down
        await asyncio.sleep(0.3)
        return count

    monkeypatch.setattr(admin_routes, "_count_admins", count_then_pause)

    responses = await asyncio.gather(
        client.post("/admin/me/step-down", headers=bearer(admin_id, "admin")),
        client.post("/admin/me/step-down", headers=bearer(deputy, "admin")),
    )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert sorted([await role_of(engine, admin_id), await role_of(engine, deputy)]) == ["admin", "student"]


async def test_an_old_admin_token_cant_promote_after_stepping_down(
    client: AsyncClient, engine: AsyncEngine, admin_id: int
) -> None:
    await add_user(engine, "deputy", "admin")
    old_token = bearer(admin_id, "admin")
    assert (await client.post("/admin/me/step-down", headers=old_token)).status_code == 200

    # The token still says admin, but the database doesn't
    response = await client.post(f"/admin/users/{admin_id}/promote", headers=old_token)

    assert response.status_code == 403
    assert await role_of(engine, admin_id) == "student"
    assert (await client.post("/admin/me/step-down", headers=old_token)).status_code == 403


async def test_a_promotion_reaches_the_next_access_token(client: AsyncClient, admin_id: int) -> None:
    alice = {"email": "alice@u.nus.edu", "username": "alice", "password": "S3cret-pass"}
    registered = await client.post("/auth/register", json=alice)
    tokens = (await client.post("/auth/login", data={"username": "alice", "password": alice["password"]})).json()

    await client.post(f"/admin/users/{registered.json()['id']}/promote", headers=bearer(admin_id, "admin"))
    refreshed = (await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).json()

    assert jwt.decode(refreshed["access_token"], options={"verify_signature": False})["role"] == "admin"
