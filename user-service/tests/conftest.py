# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated pytest fixtures: a disposable Postgres container migrated with Alembic, per-test empty tables,
#        and an HTTP client for the app wired to the test database; AI-added a test JWT_SECRET default (2026-09-27);
#        AI-replaced it with a per-run RSA key pair for RS256 signing (2026-11-09).
# Author review: reviewed by Nathan

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# main.py reads settings on import; the tests swap in their own engine, so this URL is never used
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused@localhost/unused")
# A fresh signing key per test run. Set before test modules import, since test_auth.py signs tokens at import time.
os.environ["JWT_PRIVATE_KEY"] = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    .decode()
)

import pytest
from httpx import ASGITransport, AsyncClient
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from user_service.db import get_engine
from user_service.main import app
from user_service.tables import metadata

ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    return Config(ALEMBIC_INI)


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
async def database_url(postgres_url: str, alembic_config: Config) -> str:
    # Build the schema the same way deployments do, once per test run
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(upgrade_to_head, alembic_config)
    await engine.dispose()
    return postgres_url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    # Every test starts from empty tables
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
