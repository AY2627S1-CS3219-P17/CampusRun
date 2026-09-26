# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated test fixtures: a migrated test database, a test client and token helpers.
# Author review: <to be completed by author>

"""Tests run against a real Postgres, migrated with Alembic.

The test database is the DATABASE_URL database with "_test" added to its name
(supplier_service_test), created if missing and rebuilt from the migrations at
the start of every run. Override it with TEST_DATABASE_URL. The dev database is
never touched.
"""

import asyncio
import os
import time

import jwt
import pytest

TEST_SECRET = "test-secret-that-is-long-enough-for-hs256-0123456789"
os.environ["JWT_SECRET"] = TEST_SECRET

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import make_url, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from supplier_service.config import SERVICE_ROOT, Settings, get_settings  # noqa: E402


def _test_database_url() -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    base = make_url(Settings().database_url.get_secret_value())  # pyright: ignore[reportCallIssue]
    return base.set(database=f"{base.database}_test").render_as_string(hide_password=False)


TEST_DATABASE_URL = _test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
get_settings.cache_clear()

from supplier_service.db import create_engine  # noqa: E402
from supplier_service.main import app  # noqa: E402

ALEMBIC_CONFIG = Config(str(SERVICE_ROOT / "alembic.ini"))


async def _recreate_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    if not url.database or not url.database.endswith("_test"):
        raise RuntimeError("Refusing to run tests against a database whose name does not end in _test.")
    server = create_async_engine(url.set(database="postgres"), poolclass=NullPool, isolation_level="AUTOCOMMIT")
    async with server.connect() as conn:
        if not await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": url.database}):
            await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    await server.dispose()

    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    asyncio.run(_recreate_database())
    command.upgrade(ALEMBIC_CONFIG, "head")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def engine():
    engine = create_engine(get_settings(), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE suppliers, delivery_locations RESTART IDENTITY"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(engine):
    app.state.engine = engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def make_token(role: str = "student", sub: str = "user-1", *, expires_in: int = 3600, secret: str = TEST_SECRET) -> str:
    now = int(time.time())
    return jwt.encode({"sub": sub, "role": role, "iat": now, "exp": now + expires_in}, secret, algorithm="HS256")


def auth(role: str = "student", sub: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(role, sub or f'{role}-1')}"}


STUDENT = auth("student")
ADMIN = auth("admin")


def supplier_body(**overrides) -> dict:
    body = {
        "name": "Test Kiosk",
        "type": "Food",
        "building": "COM3",
        "floor": "1",
        "locationDescription": "Next to the lift lobby",
        "latitude": 1.2949,
        "longitude": 103.7744,
        "startTime": "08:00",
        "endTime": "20:00",
    }
    return body | overrides
