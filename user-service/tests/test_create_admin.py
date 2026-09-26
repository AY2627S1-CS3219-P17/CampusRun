# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated tests for the create-initial-admin script.
# Author review: <to be completed by author>

import asyncio

import pytest
from pydantic import SecretStr
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.config import Settings
from user_service.scripts.create_admin import create_initial_admin
from user_service.security import password_hash
from user_service.tables import USERNAME_MAX_LENGTH, admins

pytestmark = pytest.mark.anyio


def make_settings(database_url: str, username: str | None, password: str | None) -> Settings:
    # _env_file=None so values in a local .env can't leak into the test
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr(database_url),
        initial_admin_username=username,
        initial_admin_password=SecretStr(password) if password is not None else None,
    )


async def fetch_admins(engine: AsyncEngine) -> list[tuple[str, str]]:
    async with engine.connect() as conn:
        result = await conn.execute(select(admins.c.username, admins.c.password_hash))
        return [(row.username, row.password_hash) for row in result]


async def test_creates_admin_with_hashed_password(engine: AsyncEngine, database_url: str) -> None:
    message = await create_initial_admin(make_settings(database_url, "  root  ", "s3cret-pass"))

    assert message == "Created initial admin 'root'"
    [(username, stored_hash)] = await fetch_admins(engine)
    assert username == "root"
    assert stored_hash != "s3cret-pass"
    assert password_hash.verify("s3cret-pass", stored_hash)


async def test_rerun_is_a_no_op(engine: AsyncEngine, database_url: str) -> None:
    settings = make_settings(database_url, "root", "s3cret-pass")
    await create_initial_admin(settings)
    [first] = await fetch_admins(engine)

    message = await create_initial_admin(settings)

    assert message == "Skipped: an admin already exists"
    assert await fetch_admins(engine) == [first]


async def test_skips_when_a_different_admin_exists(engine: AsyncEngine, database_url: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(insert(admins).values(username="existing", password_hash="x"))

    message = await create_initial_admin(make_settings(database_url, "root", "s3cret-pass"))

    assert message == "Skipped: an admin already exists"
    assert await fetch_admins(engine) == [("existing", "x")]


async def test_concurrent_runs_create_exactly_one_admin(engine: AsyncEngine, database_url: str) -> None:
    settings = make_settings(database_url, "root", "s3cret-pass")

    messages = await asyncio.gather(create_initial_admin(settings), create_initial_admin(settings))

    assert sorted(messages) == ["Created initial admin 'root'", "Skipped: an admin already exists"]
    assert len(await fetch_admins(engine)) == 1


@pytest.mark.parametrize(
    ("username", "password"),
    [(None, "s3cret-pass"), ("root", None), ("   ", "s3cret-pass"), ("root", "")],
)
async def test_rejects_missing_credentials(
    engine: AsyncEngine, database_url: str, username: str | None, password: str | None
) -> None:
    with pytest.raises(ValueError, match="must both be set"):
        await create_initial_admin(make_settings(database_url, username, password))

    assert await fetch_admins(engine) == []


async def test_rejects_overlong_username(engine: AsyncEngine, database_url: str) -> None:
    username = "a" * (USERNAME_MAX_LENGTH + 1)

    with pytest.raises(ValueError, match=f"at most {USERNAME_MAX_LENGTH} characters"):
        await create_initial_admin(make_settings(database_url, username, "s3cret-pass"))

    assert await fetch_admins(engine) == []
