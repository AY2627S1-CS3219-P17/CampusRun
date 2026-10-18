# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated tests that the migrations match tables.py and that Postgres itself rejects inconsistent
#        errands (own courier, reward out of range, courier missing or present in the wrong state, cancel reason).
# Author review: <to be completed by author>

from datetime import UTC, datetime, timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.tables import errands, metadata

pytestmark = pytest.mark.anyio


def schema_differences(connection: Connection) -> list:
    return compare_metadata(MigrationContext.configure(connection), metadata)


async def test_migrations_match_table_definitions(engine: AsyncEngine) -> None:
    # Fails when tables.py changes without a matching migration (or vice versa)
    async with engine.connect() as conn:
        differences = await conn.run_sync(schema_differences)
    assert differences == []


def errand(**overrides) -> dict:
    values = {
        "requester_id": 1,
        "state": "OPEN",
        "credit_status": "PENDING",
        "title": "Collect printed notes",
        "reward": 10,
        "supplier_id": 1,
        "delivery_location_id": 1,
        "deliver_by": datetime.now(UTC) + timedelta(hours=1),
    }
    return values | overrides


async def insert_errand(engine: AsyncEngine, **overrides) -> None:
    async with engine.begin() as conn:
        await conn.execute(insert(errands).values(**errand(**overrides)))


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"state": "ACCEPTED", "courier_id": 2, "credit_status": "HELD"},
        {"state": "COMPLETED", "courier_id": 2, "credit_status": "TRANSFERRED"},
        {"state": "CANCELLED", "cancel_reason": "REQUESTER"},
        {"state": "EXPIRED"},
        {"state": "EXPIRED", "courier_id": 2},
        {"reward": 1},
        {"reward": 100},
    ],
    ids=["open", "accepted", "completed", "cancelled", "expired-unaccepted", "expired-accepted", "reward-1", "reward-100"],
)
async def test_consistent_errands_are_accepted(engine: AsyncEngine, overrides: dict) -> None:
    await insert_errand(engine, **overrides)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"state": "ACCEPTED", "courier_id": 1}, "ck_errands_courier_is_not_requester"),
        ({"reward": 0}, "ck_errands_reward_range"),
        ({"reward": 101}, "ck_errands_reward_range"),
        ({"courier_id": 2}, "ck_errands_no_courier_before_accept"),
        ({"state": "PICKED_UP"}, "ck_errands_courier_once_accepted"),
        ({"state": "COMPLETED"}, "ck_errands_courier_once_accepted"),
        ({"state": "CANCELLED"}, "ck_errands_cancel_reason_only_when_cancelled"),
        ({"cancel_reason": "REQUESTER"}, "ck_errands_cancel_reason_only_when_cancelled"),
        ({"state": "CANCELLED", "cancel_reason": "BORED"}, "ck_errands_cancel_reason"),
        ({"state": "LOST"}, "ck_errands_state"),
        ({"credit_status": "SPENT"}, "ck_errands_credit_status"),
    ],
    ids=[
        "own-courier",
        "reward-0",
        "reward-101",
        "courier-while-open",
        "picked-up-without-courier",
        "completed-without-courier",
        "cancelled-without-reason",
        "reason-while-open",
        "unknown-cancel-reason",
        "unknown-state",
        "unknown-credit-status",
    ],
)
async def test_postgres_rejects_inconsistent_errands(engine: AsyncEngine, overrides: dict, constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await insert_errand(engine, **overrides)
