# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated pytest fixtures following user-service/tests/conftest.py: a disposable Postgres container
#        migrated with Alembic, per-test empty tables, an HTTP client wired to the test database, and token helpers.
# Author review: <to be completed by author>

import os
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

TEST_SECRET = "test-secret-that-is-at-least-32-characters-long"
# main.py reads settings on import; the tests swap in their own engine, so this URL is never used
os.environ["DATABASE_URL"] = "postgresql+asyncpg://unused@localhost/unused"
os.environ["JWT_SECRET"] = TEST_SECRET
# Keep a developer's real Groq key in order-service/.env out of the tests
os.environ["GROQ_API_KEY"] = ""

import jwt  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import Connection, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine  # noqa: E402
from testcontainers.community.postgres import PostgresContainer  # noqa: E402

from order_service.db import get_engine  # noqa: E402
from order_service.main import app  # noqa: E402
from order_service.tables import metadata  # noqa: E402

ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def make_token(user_id: int = 1, role: str = "student", *, expires_in: int = 300, secret: str = TEST_SECRET) -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "role": role, "iat": now, "exp": now + expires_in}, secret, algorithm="HS256")


def auth(user_id: int = 1, role: str = "student") -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id, role)}"}


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


def upgrade_to_head(connection: Connection, config: Config) -> None:
    # env.py uses this connection instead of reading DATABASE_URL from settings
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    # Throwaway container, so tests never touch the dev database or its data
    with PostgresContainer("postgres:18", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
async def database_url(postgres_url: str) -> str:
    # Build the schema the same way deployments do, once per test run
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(upgrade_to_head, Config(ALEMBIC_INI))
    await engine.dispose()
    return postgres_url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    # Every test starts from empty tables
    if metadata.sorted_tables:
        table_names = ", ".join(table.name for table in metadata.sorted_tables)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    # ASGITransport skips the lifespan, so point the app at the test engine directly
    app.dependency_overrides[get_engine] = lambda: engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
