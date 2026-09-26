# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated check that the Alembic migrations match the table definitions.
# Author review: reviewed by Nathan

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.tables import metadata

pytestmark = pytest.mark.anyio


def schema_differences(connection: Connection) -> list:
    return compare_metadata(MigrationContext.configure(connection), metadata)


async def test_migrations_match_table_definitions(engine: AsyncEngine) -> None:
    # Fails when tables.py changes without a matching migration (or vice versa)
    async with engine.connect() as conn:
        differences = await conn.run_sync(schema_differences)

    assert differences == []
