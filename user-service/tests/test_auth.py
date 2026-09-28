# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
# Scope: AI-generated tests for password login, JWT validation and the /users/me and /admins/me endpoints;
#        AI-updated for the "student" token type (Claude Code, 2026-09-27);
#        AI-updated for admins as users with the admin role and the "role" claim (Claude Code, 2026-09-28);
#        AI-replaced the require_student checks: both roles pass require_user (Claude Code, 2026-09-28).
# Author review: <to be completed by author>

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.auth import require_admin, require_user
from user_service.config import get_settings
from user_service.security import ALGORITHM, password_hash
from user_service.tables import users

pytestmark = pytest.mark.anyio

USER = {"email": "alice@u.nus.edu", "username": "alice", "password": "S3cret-pass"}
ADMIN = {"email": "root@u.nus.edu", "username": "root", "password": "Adm1n-pass"}


@pytest.fixture
async def user(client: AsyncClient) -> dict:
    response = await client.post("/auth/register", json=USER)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
async def admin(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            insert(users).values(
                email=ADMIN["email"],
                username=ADMIN["username"],
                password_hash=password_hash.hash(ADMIN["password"]),
                role="admin",
            )
        )


async def login(client: AsyncClient, username: str, password: str):
    # data= sends a form body, which OAuth2PasswordRequestForm expects
    return await client.post("/auth/login", data={"username": username, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_token(secret: str | None = None, **overrides) -> str:
    claims = {"sub": "1", "role": "student", "exp": datetime.now(UTC) + timedelta(minutes=5), **overrides}
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
    assert claims["role"] == "student"


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
    assert response.json()["role"] == "student"


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
        make_token(role=None),  # no role
        make_token(role=None, type="student"),  # the old claim name
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


async def test_admin_logs_in_like_a_student(client: AsyncClient, admin: None) -> None:
    response = await login(client, ADMIN["email"], ADMIN["password"])

    assert response.status_code == 200
    token = response.json()["access_token"]
    assert jwt.decode(token, options={"verify_signature": False})["role"] == "admin"

    me = await client.get("/users/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["username"] == "root"
    assert me.json()["role"] == "admin"


async def check(dependency, token: str) -> int:
    # Runs the dependency chain directly, since no route in this service is admin-only yet
    try:
        account = await require_user(token, get_settings())
        await dependency(account)
    except HTTPException as error:
        return error.status_code
    return 200


async def test_role_checks(client: AsyncClient, user: dict, admin: None) -> None:
    student_token = (await login(client, "alice", USER["password"])).json()["access_token"]
    admin_token = (await login(client, "root", ADMIN["password"])).json()["access_token"]

    # Admins keep every student capability, so any-user routes accept both roles
    assert (await require_user(student_token, get_settings())).role == "student"
    assert (await require_user(admin_token, get_settings())).role == "admin"
    assert await check(require_admin, admin_token) == 200
    assert await check(require_admin, student_token) == 403
