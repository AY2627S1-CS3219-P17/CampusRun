# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for the delivery location seed, following supplier-service/tests/test_seed.py.
# Author review: <to be completed by author>

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.config import get_settings
from order_service.seed import delivery_location_from_row, read_csv, seed_if_empty
from order_service.tables import delivery_locations

pytestmark = pytest.mark.anyio


def test_every_seed_row_is_valid() -> None:
    rows = read_csv(get_settings().seed_dir / "delivery-locations.csv")
    assert len(rows) == 100
    for row in rows:
        delivery_location_from_row(row)


async def test_seed_runs_once_and_marks_the_rows_predefined(engine: AsyncEngine) -> None:
    seed_dir = get_settings().seed_dir
    async with engine.begin() as conn:
        await seed_if_empty(conn, seed_dir)
        await seed_if_empty(conn, seed_dir)
        rows = (await conn.execute(select(delivery_locations.c.predefined, delivery_locations.c.created_by))).all()
    assert len(rows) == len(read_csv(seed_dir / "delivery-locations.csv"))
    assert all(predefined and created_by is None for predefined, created_by in rows)


async def test_students_own_locations_dont_stop_the_seed(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            delivery_locations.insert().values(name="My hall", latitude=1.3, longitude=103.77, created_by=1)
        )
        await seed_if_empty(conn, get_settings().seed_dir)
        count = await conn.scalar(select(func.count()).select_from(delivery_locations))
    assert count == 101
