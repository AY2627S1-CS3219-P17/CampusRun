# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-generated tests for refresh sessions: rotation, reuse detection, logout, expiry, password change, role
#        changes reaching the next access token, and concurrent refreshes with one token.
# Author review: I ran the tests; rotation, reuse detection and expiry pass.

import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.tables import refresh_sessions, users

pytestmark = pytest.mark.anyio

ALICE = {"email": "alice@u.nus.edu", "username": "alice", "password": "S3cret-pass"}


async def sign_in(client: AsyncClient) -> dict:
    response = await client.post("/auth/login", data={"username": "alice", "password": ALICE["password"]})
    assert response.status_code == 200
    return response.json()


@pytest.fixture
async def tokens(client: AsyncClient) -> dict:
    assert (await client.post("/auth/register", json=ALICE)).status_code == 201
    return await sign_in(client)


async def refresh(client: AsyncClient, refresh_token: str):
    return await client.post("/auth/refresh", json={"refresh_token": refresh_token})


def claims(access_token: str) -> dict:
    return jwt.decode(access_token, options={"verify_signature": False})


async def test_login_returns_a_refresh_token_and_a_short_access_token(tokens: dict) -> None:
    assert tokens["refresh_token"]
    assert tokens["expires_in"] == 5 * 60
    access = claims(tokens["access_token"])
    assert access["exp"] - access["iat"] == 5 * 60


async def test_refresh_returns_new_tokens(client: AsyncClient, tokens: dict) -> None:
    response = await refresh(client, tokens["refresh_token"])

    assert response.status_code == 200
    body = response.json()
    assert body["refresh_token"] != tokens["refresh_token"]
    assert claims(body["access_token"])["sub"] == claims(tokens["access_token"])["sub"]
    # The new access token works
    me = await client.get("/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


async def test_each_new_refresh_token_works_in_turn(client: AsyncClient, tokens: dict) -> None:
    current = tokens["refresh_token"]
    for _ in range(3):
        response = await refresh(client, current)
        assert response.status_code == 200
        current = response.json()["refresh_token"]


async def test_reusing_a_refresh_token_ends_the_session(client: AsyncClient, tokens: dict) -> None:
    stolen = tokens["refresh_token"]
    rotated = (await refresh(client, stolen)).json()["refresh_token"]

    # The old token comes back: someone else has a copy
    reused = await refresh(client, stolen)
    assert reused.status_code == 401
    assert reused.json()["detail"] == "Your session has ended. Sign in again."

    # The revocation was committed, so the copy that moved on is dead too
    assert (await refresh(client, rotated)).status_code == 401


async def test_reuse_only_ends_that_session(client: AsyncClient, tokens: dict) -> None:
    other_tab = await sign_in(client)
    stolen = tokens["refresh_token"]
    await refresh(client, stolen)
    await refresh(client, stolen)

    assert (await refresh(client, other_tab["refresh_token"])).status_code == 200


@pytest.mark.parametrize("token", ["not-a-token", "x" * 43, ""], ids=["garbage", "unknown", "empty"])
async def test_unknown_refresh_tokens_are_refused(client: AsyncClient, tokens: dict, token: str) -> None:
    response = await refresh(client, token)
    assert response.status_code == 401


async def test_refresh_token_too_long_is_rejected_before_lookup(client: AsyncClient) -> None:
    response = await refresh(client, "x" * 129)
    assert response.status_code == 422


async def test_expired_session_is_refused(client: AsyncClient, engine: AsyncEngine, tokens: dict) -> None:
    async with engine.begin() as conn:
        await conn.execute(update(refresh_sessions).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))

    assert (await refresh(client, tokens["refresh_token"])).status_code == 401


async def test_refreshing_does_not_extend_the_session(client: AsyncClient, engine: AsyncEngine, tokens: dict) -> None:
    async with engine.connect() as conn:
        before = await conn.scalar(select(refresh_sessions.c.expires_at))
    await refresh(client, tokens["refresh_token"])
    async with engine.connect() as conn:
        assert await conn.scalar(select(refresh_sessions.c.expires_at)) == before


async def test_logout_ends_the_session(client: AsyncClient, tokens: dict) -> None:
    response = await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 204
    assert (await refresh(client, tokens["refresh_token"])).status_code == 401


async def test_logout_twice_or_with_unknown_token_is_harmless(client: AsyncClient, tokens: dict) -> None:
    for token in (tokens["refresh_token"], tokens["refresh_token"], "unknown"):
        assert (await client.post("/auth/logout", json={"refresh_token": token})).status_code == 204


async def test_logout_leaves_other_sessions(client: AsyncClient, tokens: dict) -> None:
    other_tab = await sign_in(client)
    await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert (await refresh(client, other_tab["refresh_token"])).status_code == 200


async def test_password_change_ends_every_session(client: AsyncClient, tokens: dict) -> None:
    other_tab = await sign_in(client)
    response = await client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"current_password": ALICE["password"], "new_password": "N3w-password"},
    )
    assert response.status_code == 200

    assert (await refresh(client, tokens["refresh_token"])).status_code == 401
    assert (await refresh(client, other_tab["refresh_token"])).status_code == 401


async def test_failed_password_change_keeps_sessions(client: AsyncClient, tokens: dict) -> None:
    response = await client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"current_password": "wrong-password", "new_password": "N3w-password"},
    )
    assert response.status_code == 400

    assert (await refresh(client, tokens["refresh_token"])).status_code == 200


async def test_role_change_reaches_the_next_access_token(
    client: AsyncClient, engine: AsyncEngine, tokens: dict
) -> None:
    async with engine.begin() as conn:
        await conn.execute(update(users).values(role="admin"))

    body = (await refresh(client, tokens["refresh_token"])).json()
    assert claims(body["access_token"])["role"] == "admin"


async def test_deleting_the_account_ends_its_sessions(client: AsyncClient, engine: AsyncEngine, tokens: dict) -> None:
    async with engine.begin() as conn:
        await conn.execute(users.delete())
        assert await conn.scalar(select(func.count()).select_from(refresh_sessions)) == 0

    assert (await refresh(client, tokens["refresh_token"])).status_code == 401


async def test_only_the_token_hash_is_stored(engine: AsyncEngine, tokens: dict) -> None:
    async with engine.connect() as conn:
        stored = await conn.scalar(select(refresh_sessions.c.token_hash))
    assert stored is not None
    assert tokens["refresh_token"].encode() not in stored
    assert len(stored) == 32


async def test_signing_in_clears_dead_sessions(client: AsyncClient, engine: AsyncEngine, tokens: dict) -> None:
    await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    await sign_in(client)

    async with engine.connect() as conn:
        assert await conn.scalar(select(func.count()).select_from(refresh_sessions)) == 1


async def test_concurrent_refreshes_with_one_token_let_at_most_one_through(client: AsyncClient, tokens: dict) -> None:
    # Two requests racing with the same token, as a stolen copy would. The row lock makes them take turns: the first
    # rotates, the second looks like reuse and ends the session.
    first, second = await asyncio.gather(
        refresh(client, tokens["refresh_token"]), refresh(client, tokens["refresh_token"])
    )

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 401]
    winner = first if first.status_code == 200 else second
    assert (await refresh(client, winner.json()["refresh_token"])).status_code == 401
