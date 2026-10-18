# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-generated test fixtures following supplier-service/tests/conftest.py: a migrated test database,
#        a test client, token helpers and a fake RabbitMQ message for the worker.
# Author review: <to be completed by author>

"""Tests run against a real Postgres, migrated with Alembic.

The test database is the DATABASE_URL database with "_test" added to its name (credit_service_test), created if
missing and rebuilt from the migrations at the start of every run. Override it with TEST_DATABASE_URL. RabbitMQ
isn't needed: the worker tests hand it fake messages.
"""

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field

import jwt
import pytest

TEST_SECRET = "test-secret-that-is-long-enough-for-hs256-0123456789"
os.environ["JWT_SECRET"] = TEST_SECRET
os.environ["INITIAL_CREDITS"] = "100"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import make_url, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from credit_service.config import Settings, get_settings  # noqa: E402


def _test_database_url() -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    base = make_url(Settings().database_url.get_secret_value())  # pyright: ignore[reportCallIssue]
    return base.set(database=f"{base.database}_test").render_as_string(hide_password=False)


TEST_DATABASE_URL = _test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
get_settings.cache_clear()

from credit_service.db import create_engine  # noqa: E402
from credit_service.main import app  # noqa: E402

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALEMBIC_CONFIG = Config(os.path.join(SERVICE_ROOT, "alembic.ini"))


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
    # A real pool, so concurrency tests get one connection per concurrent transaction
    engine = create_engine(get_settings(), pool_size=20, max_overflow=40)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE ledger_entries, reservations, wallets"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(engine):
    app.state.engine = engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def make_token(role: str = "student", sub: str = "1", *, expires_in: int = 3600, secret: str = TEST_SECRET) -> str:
    now = int(time.time())
    return jwt.encode({"sub": sub, "role": role, "iat": now, "exp": now + expires_in}, secret, algorithm="HS256")


def auth(user_id: int, role: str = "student") -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(role, str(user_id))}"}


@dataclass
class FakeMessage:
    """Just the parts of an aio_pika IncomingMessage the worker uses."""

    type: str
    body: bytes
    user_id: str | None
    routing_key: str
    message_id: str | None = field(default_factory=lambda: str(uuid.uuid4()))
    outcome: str | None = None

    async def ack(self):
        self.outcome = "ack"

    async def reject(self, requeue: bool = False):
        self.outcome = "requeue" if requeue else "dead-letter"


@dataclass
class FakeExchange:
    published: list = field(default_factory=list)

    async def publish(self, message, routing_key: str):
        self.published.append((routing_key, message))
