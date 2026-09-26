# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated tests for the POST /auth/register endpoint.
# Author review: reviewed by Nathan

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.schemas import PASSWORD_MAX_LENGTH
from user_service.security import password_hash
from user_service.tables import USERNAME_MAX_LENGTH, users

pytestmark = pytest.mark.anyio

VALID = {"email": "alice@u.nus.edu", "username": "alice", "password": "s3cret-pass"}


async def count_users(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return await conn.scalar(select(func.count()).select_from(users)) or 0


async def test_creates_user_with_hashed_password(client: AsyncClient, engine: AsyncEngine) -> None:
    response = await client.post("/auth/register", json=VALID)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@u.nus.edu"
    assert body["username"] == "alice"
    assert body["email_verified_at"] is None
    assert "password" not in body and "password_hash" not in body

    async with engine.connect() as conn:
        stored_hash = (
            await conn.execute(select(users.c.password_hash).where(users.c.id == body["id"]))
        ).scalar_one()
    assert stored_hash != VALID["password"]
    assert password_hash.verify(VALID["password"], stored_hash)


async def test_strips_username_whitespace(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={**VALID, "username": "  alice  "})

    assert response.status_code == 201
    assert response.json()["username"] == "alice"


async def test_accepts_staff_email(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={**VALID, "email": "prof@nus.edu.sg"})

    assert response.status_code == 201


@pytest.mark.parametrize(
    "duplicate",
    [
        {"email": "ALICE@u.nus.edu", "username": "someone-else"},
        {"email": "other@u.nus.edu", "username": "ALICE"},
    ],
)
async def test_rejects_case_insensitive_duplicates(
    client: AsyncClient, engine: AsyncEngine, duplicate: dict[str, str]
) -> None:
    await client.post("/auth/register", json=VALID)

    response = await client.post("/auth/register", json={**VALID, **duplicate})

    assert response.status_code == 409
    # Same message either way, so it doesn't reveal which field is taken
    assert response.json()["detail"] == "Username or email is already in use"
    assert await count_users(engine) == 1


async def test_concurrent_registrations_create_exactly_one_user(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    responses = await asyncio.gather(
        client.post("/auth/register", json=VALID),
        client.post("/auth/register", json=VALID),
    )

    assert sorted(r.status_code for r in responses) == [201, 409]
    assert await count_users(engine) == 1


@pytest.mark.parametrize(
    "field",
    [
        {"email": "not-an-email"},
        {"email": "alice@gmail.com"},
        {"email": "alice@fake-u.nus.edu.evil.com"},
        {"username": "ab"},
        {"username": "a" * (USERNAME_MAX_LENGTH + 1)},
        {"username": "has space"},
        {"username": "emoji😀"},
        {"password": "short"},
        {"password": "a" * (PASSWORD_MAX_LENGTH + 1)},
    ],
)
async def test_rejects_invalid_input(
    client: AsyncClient, engine: AsyncEngine, field: dict[str, str]
) -> None:
    response = await client.post("/auth/register", json={**VALID, **field})

    assert response.status_code == 422
    assert await count_users(engine) == 0


@pytest.mark.parametrize("missing", ["email", "username", "password"])
async def test_rejects_missing_fields(client: AsyncClient, missing: str) -> None:
    body = {key: value for key, value in VALID.items() if key != missing}

    response = await client.post("/auth/register", json=body)

    assert response.status_code == 422
