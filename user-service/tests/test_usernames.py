# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for GET /internal/usernames: the users returned, never an email, and input limits.
# Author review: <to be completed by author>

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.config import get_settings
from user_service.security import create_access_token
from user_service.tables import users

pytestmark = pytest.mark.anyio


@pytest.fixture
async def user_ids(engine: AsyncEngine) -> list[int]:
    async with engine.begin() as conn:
        result = await conn.execute(
            insert(users)
            .values([{"email": f"u{i}@u.nus.edu", "username": f"user{i}", "password_hash": "x"} for i in range(3)])
            .returning(users.c.id)
        )
        return list(result.scalars())


def bearer(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, 'student', get_settings())}"}


async def test_returns_the_requested_users_usernames_only(client: AsyncClient, user_ids: list[int]) -> None:
    first, _, third = user_ids
    response = await client.get(
        f"/internal/usernames?ids={third}&ids={first}&ids=999999&ids={first}", headers=bearer(first)
    )

    assert response.status_code == 200
    # Ordered by id, each once; unknown ids are left out; no email address or other account details
    assert response.json() == [{"id": first, "username": "user0"}, {"id": third, "username": "user2"}]


async def test_requires_a_token(client: AsyncClient, user_ids: list[int]) -> None:
    response = await client.get(f"/internal/usernames?ids={user_ids[0]}")
    assert response.status_code == 401


@pytest.mark.parametrize(
    "query",
    ["", "?ids=0", "?ids=abc", "?" + "&".join(f"ids={i}" for i in range(1, 102))],
    ids=["none", "zero", "not-a-number", "over-100"],
)
async def test_rejects_bad_ids(client: AsyncClient, user_ids: list[int], query: str) -> None:
    response = await client.get(f"/internal/usernames{query}", headers=bearer(user_ids[0]))
    assert response.status_code == 422
