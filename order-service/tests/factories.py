# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated helpers that write delivery locations and errands straight to the test database, and read the
#        outbox, shared by the errand tests.
# Author review: <to be completed by author>

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.tables import delivery_locations, errands, outbox

ALICE, BOB, CAROL = 1, 2, 3


async def count(engine: AsyncEngine, table) -> int:
    async with engine.connect() as conn:
        return await conn.scalar(select(func.count()).select_from(table))


async def outbox_rows(engine: AsyncEngine) -> list:
    async with engine.connect() as conn:
        return list(await conn.execute(select(outbox).order_by(outbox.c.id)))


async def add_location(engine: AsyncEngine, **values) -> int:
    defaults = {"name": "COM3", "latitude": 1.29494, "longitude": 103.77438, "predefined": True}
    async with engine.begin() as conn:
        return await conn.scalar(
            insert(delivery_locations).values(**defaults | values).returning(delivery_locations.c.id)
        )


async def add_errand(engine: AsyncEngine, location_id: int, **values) -> int:
    """An errand in any state, written directly. Defaults: Alice's, OPEN, credits HELD, due in an hour."""
    defaults = {
        "requester_id": ALICE,
        "state": "OPEN",
        "credit_status": "HELD",
        "title": "Collect printed notes",
        "reward": 10,
        "supplier_id": 1,
        "delivery_location_id": location_id,
        "deliver_by": datetime.now(UTC) + timedelta(hours=1),
    }
    async with engine.begin() as conn:
        return await conn.scalar(insert(errands).values(**defaults | values).returning(errands.c.id))


async def errand_row(engine: AsyncEngine, errand_id: int):
    async with engine.connect() as conn:
        return (await conn.execute(select(errands).where(errands.c.id == errand_id))).one()
