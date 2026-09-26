# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
# Scope: AI-generated tests for password login, JWT validation and the /users/me and /admins/me endpoints;
#        AI-updated for the "student" token type (Claude Code, 2026-09-27).
# Author review: <to be completed by author>

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.config import get_settings
from user_service.security import ALGORITHM, password_hash
from user_service.tables import admins, users

pytestmark = pytest.mark.anyio

USER = {"email": "alice@u.nus.edu", "username": "alice", "password": "S3cret-pass"}
ADMIN = {"username": "root", "password": "admin-pass"}


@pytest.fixture
async def user(client: AsyncClient) -> dict:
    response = await client.post("/auth/register", json=USER)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
async def admin(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            insert(admins).values(
                username=ADMIN["username"], password_hash=password_hash.hash(ADMIN["password"])
            )
        )


async def login(client: AsyncClient, username: str, password: str, path: str = "/auth/login"):
    # data= sends a form body, which OAuth2PasswordRequestForm expects
    return await client.post(path, data={"username": username, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_token(secret: str | None = None, **overrides) -> str:
    claims = {"sub": "1", "type": "student", "exp": datetime.now(UTC) + timedelta(minutes=5), **overrides}
    # A claim set to None means "leave it out"
    claims = {key: value for key, value in claims.items() if value is not None}
    return jwt.encode(claims, secret or get_settings().jwt_secret.get_secret_value(), algorithm=ALGORITHM)


@pytest.mark.parametrize("identifier", ["alice@u.nus.edu", "ALICE@U.NUS.EDU", "alice", "Alice", "  alice  "])
async def test_login_accepts_email_or_username(client: AsyncClient, user: dict, identifier: str) -> None:
    response = await login(client, identifier, USER["password"])

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["sub"] == str(user["id"])
    assert claims["type"] == "student"


@pytest.mark.parametrize(
    ("identifier", "password"),
    [("alice", "wrong-password"), ("nobody", USER["password"]), ("alice", "x" * 10_000)],
)
async def test_login_failures_look_identical(
    client: AsyncClient, user: dict, identifier: str, password: str
) -> None:
    response = await login(client, identifier, password)

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect login or password"


async def test_me_returns_current_user(client: AsyncClient, user: dict) -> None:
    token = (await login(client, "alice", USER["password"])).json()["access_token"]

    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["username"] == "alice"


async def test_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        make_token(exp=datetime.now(UTC) - timedelta(minutes=1)),  # expired
        make_token(secret="some-other-secret-that-is-32-chars-long!"),  # forged
        make_token(exp=None),  # no expiry
        make_token(type=None),  # no account type
    ],
)
async def test_me_rejects_invalid_tokens(client: AsyncClient, user: dict, token: str) -> None:
    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 401


async def test_me_rejects_token_for_deleted_account(
    client: AsyncClient, engine: AsyncEngine, user: dict
) -> None:
    token = (await login(client, "alice", USER["password"])).json()["access_token"]
    async with engine.begin() as conn:
        await conn.execute(delete(users).where(users.c.id == user["id"]))

    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 401


async def test_admin_login_and_me(client: AsyncClient, admin: None) -> None:
    token = (await login(client, "root", ADMIN["password"], "/auth/admin/login")).json()["access_token"]

    response = await client.get("/admins/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["username"] == "root"


async def test_tokens_only_work_for_their_account_type(
    client: AsyncClient, user: dict, admin: None
) -> None:
    user_token = (await login(client, "alice", USER["password"])).json()["access_token"]
    admin_token = (await login(client, "root", ADMIN["password"], "/auth/admin/login")).json()["access_token"]

    # Both accounts have id 1, so only the "type" claim tells them apart
    assert (await client.get("/admins/me", headers=bearer(user_token))).status_code == 403
    assert (await client.get("/users/me", headers=bearer(admin_token))).status_code == 403


async def test_user_login_rejects_admin_credentials(client: AsyncClient, admin: None) -> None:
    response = await login(client, "root", ADMIN["password"])

    assert response.status_code == 401
