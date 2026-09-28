# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated tests for the create-initial-admin script; AI-rewrote them for admins as users with the
#        admin role, and added the --skip-if-unset cases (2026-09-28).
# Author review: reviewed by Nathan

import asyncio

import pytest
from pydantic import SecretStr
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.config import Settings
from user_service.scripts.create_admin import create_initial_admin
from user_service.security import password_hash
from user_service.tables import USERNAME_MAX_LENGTH, users

pytestmark = pytest.mark.anyio

EMAIL = "root@u.nus.edu"
PASSWORD = "S3cret-pass"


def make_settings(
    database_url: str, email: str | None = EMAIL, username: str | None = "root", password: str | None = PASSWORD
) -> Settings:
    # _env_file=None so values in a local .env can't leak into the test
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr(database_url),
        initial_admin_email=email,
        initial_admin_username=username,
        initial_admin_password=SecretStr(password) if password is not None else None,
    )


async def fetch_users(engine: AsyncEngine) -> list[tuple[str, str, str]]:
    async with engine.connect() as conn:
        result = await conn.execute(select(users.c.email, users.c.username, users.c.role).order_by(users.c.id))
        return [(row.email, row.username, row.role) for row in result]


async def insert_user(engine: AsyncEngine, email: str, username: str, role: str = "student") -> None:
    async with engine.begin() as conn:
        await conn.execute(insert(users).values(email=email, username=username, password_hash="x", role=role))


async def test_creates_admin_user_with_hashed_password(engine: AsyncEngine, database_url: str) -> None:
    message = await create_initial_admin(make_settings(database_url, email=f"  {EMAIL}  ", username="  root  "))

    assert message == "Created initial admin 'root'"
    assert await fetch_users(engine) == [(EMAIL, "root", "admin")]
    async with engine.connect() as conn:
        stored_hash = await conn.scalar(select(users.c.password_hash))
    assert stored_hash != PASSWORD
    assert password_hash.verify(PASSWORD, stored_hash)


async def test_rerun_is_a_no_op(engine: AsyncEngine, database_url: str) -> None:
    settings = make_settings(database_url)
    await create_initial_admin(settings)
    first = await fetch_users(engine)

    message = await create_initial_admin(settings)

    assert message == "Skipped: an admin already exists"
    assert await fetch_users(engine) == first


async def test_skips_when_a_different_admin_exists(engine: AsyncEngine, database_url: str) -> None:
    await insert_user(engine, "existing@u.nus.edu", "existing", role="admin")

    message = await create_initial_admin(make_settings(database_url))

    assert message == "Skipped: an admin already exists"
    assert await fetch_users(engine) == [("existing@u.nus.edu", "existing", "admin")]


async def test_ignores_students_when_checking_for_an_admin(engine: AsyncEngine, database_url: str) -> None:
    await insert_user(engine, "alice@u.nus.edu", "alice")

    message = await create_initial_admin(make_settings(database_url))

    assert message == "Created initial admin 'root'"
    assert [role for *_, role in await fetch_users(engine)] == ["student", "admin"]


@pytest.mark.parametrize(("email", "username"), [(EMAIL, "someone"), ("someone@u.nus.edu", "ROOT")])
async def test_rejects_email_or_username_used_by_a_student(
    engine: AsyncEngine, database_url: str, email: str, username: str
) -> None:
    await insert_user(engine, email, username)

    with pytest.raises(ValueError, match="already used by another account"):
        await create_initial_admin(make_settings(database_url))

    assert await fetch_users(engine) == [(email, username, "student")]


async def test_concurrent_runs_create_exactly_one_admin(engine: AsyncEngine, database_url: str) -> None:
    settings = make_settings(database_url)

    messages = await asyncio.gather(create_initial_admin(settings), create_initial_admin(settings))

    assert sorted(messages) == ["Created initial admin 'root'", "Skipped: an admin already exists"]
    assert len(await fetch_users(engine)) == 1


@pytest.mark.parametrize(
    ("email", "username", "password"),
    [
        (None, "root", PASSWORD),
        (EMAIL, None, PASSWORD),
        (EMAIL, "root", None),
        ("   ", "root", PASSWORD),
        (EMAIL, "   ", PASSWORD),
        (EMAIL, "root", ""),
    ],
)
async def test_rejects_missing_values(
    engine: AsyncEngine, database_url: str, email: str | None, username: str | None, password: str | None
) -> None:
    with pytest.raises(ValueError, match="must all be set"):
        await create_initial_admin(make_settings(database_url, email, username, password))

    assert await fetch_users(engine) == []


async def test_skip_if_unset_skips_when_nothing_is_set(engine: AsyncEngine, database_url: str) -> None:
    settings = make_settings(database_url, email=None, username=None, password=None)

    message = await create_initial_admin(settings, skip_if_unset=True)

    assert message == "Skipped: INITIAL_ADMIN_* not set"
    assert await fetch_users(engine) == []


async def test_skip_if_unset_still_rejects_partial_values(engine: AsyncEngine, database_url: str) -> None:
    with pytest.raises(ValueError, match="must all be set"):
        await create_initial_admin(make_settings(database_url, password=None), skip_if_unset=True)

    assert await fetch_users(engine) == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"email": "prof@nus.edu.sg"}, "INITIAL_ADMIN_EMAIL must be an NUS student email"),
        ({"email": "not-an-email"}, "INITIAL_ADMIN_EMAIL"),
        ({"username": "a" * (USERNAME_MAX_LENGTH + 1)}, f"at most {USERNAME_MAX_LENGTH} characters"),
        ({"password": "weakpassword"}, "INITIAL_ADMIN_PASSWORD"),
    ],
)
async def test_applies_registration_rules(
    engine: AsyncEngine, database_url: str, overrides: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        await create_initial_admin(make_settings(database_url, **overrides))

    assert await fetch_users(engine) == []
