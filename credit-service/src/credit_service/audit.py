# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for consistency audit: re-derives balances from the ledger, checks conservation of credits
#        and lists holds that have waited too long for a transfer or release.
# Author review: <to be completed by author>

"""Checks the invariants of the credit economy. Run with `credit-audit`, or GET /admin/audit as an admin.

1. Every wallet's balances equal the sum of its ledger entries (N5.2.1).
2. Every wallet's reserved balance equals the credits held by its HELD reservations.
3. Credits in circulation equal credits ever allocated: nothing was created or destroyed (F14.1.1).
4. Every TRANSFERRED reservation has its two ledger entries, for the same amount.
5. Holds older than STALE_HOLD_HOURS are listed: an errand can't stay open that long, so the Order Service
   probably has an errand that ended without its transfer or release reaching this service. They're warnings,
   not failures: the Order Service's records decide what should happen to them.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from credit_service.config import get_settings
from credit_service.db import create_engine
from credit_service.tables import EntryKind, ReservationStatus, ledger_entries, reservations, wallets


class _Report(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, serialize_by_alias=True)


class StaleHold(_Report):
    errand_id: int
    requester_id: int
    amount: int
    held_since: datetime


class AuditReport(_Report):
    ok: bool
    checked_at: datetime
    wallets: int
    total_allocated: int
    total_in_circulation: int
    total_available: int
    total_reserved: int
    problems: list[str]
    stale_holds: list[StaleHold]


async def run_audit(conn: AsyncConnection, *, stale_hold_hours: int) -> AuditReport:
    problems: list[str] = []

    # 1. Balances re-derived from the ledger alone
    ledger = (
        select(
            ledger_entries.c.user_id,
            func.sum(ledger_entries.c.available_delta).label("available"),
            func.sum(ledger_entries.c.reserved_delta).label("reserved"),
        )
        .group_by(ledger_entries.c.user_id)
        .subquery()
    )
    for row in await conn.execute(
        select(wallets.c.user_id, wallets.c.available, wallets.c.reserved, ledger.c.available, ledger.c.reserved)
        .select_from(wallets.outerjoin(ledger, ledger.c.user_id == wallets.c.user_id))
        .where(
            or_(
                wallets.c.available != func.coalesce(ledger.c.available, 0),
                wallets.c.reserved != func.coalesce(ledger.c.reserved, 0),
            )
        )
    ):
        problems.append(
            f"Wallet {row[0]} holds {row[1]} available / {row[2]} reserved, "
            f"but its ledger adds up to {row[3] or 0} / {row[4] or 0}"
        )

    # 2. Reserved balance = what its holds add up to
    held = (
        select(reservations.c.requester_id, func.sum(reservations.c.amount).label("held"))
        .where(reservations.c.status == ReservationStatus.HELD)
        .group_by(reservations.c.requester_id)
        .subquery()
    )
    for row in await conn.execute(
        select(wallets.c.user_id, wallets.c.reserved, func.coalesce(held.c.held, 0))
        .select_from(wallets.outerjoin(held, held.c.requester_id == wallets.c.user_id))
        .where(wallets.c.reserved != func.coalesce(held.c.held, 0))
    ):
        problems.append(f"Wallet {row[0]} has {row[1]} reserved, but its held reservations add up to {row[2]}")

    # 3. Conservation
    totals = (
        await conn.execute(
            select(
                func.count(),
                func.coalesce(func.sum(wallets.c.available), 0),
                func.coalesce(func.sum(wallets.c.reserved), 0),
                func.coalesce(func.sum(wallets.c.total), 0),
            ).select_from(wallets)
        )
    ).one()
    allocated = await conn.scalar(
        select(func.coalesce(func.sum(ledger_entries.c.available_delta), 0)).where(
            ledger_entries.c.kind == EntryKind.INITIAL_ALLOCATION
        )
    )
    if totals[3] != allocated:
        problems.append(f"{totals[3]} credits are in circulation, but {allocated} were ever allocated")

    # 4. Each transfer has both halves
    out_entry = ledger_entries.alias("out_entry")
    in_entry = ledger_entries.alias("in_entry")
    for row in await conn.execute(
        select(reservations.c.errand_id)
        .select_from(
            reservations.outerjoin(
                out_entry,
                and_(
                    out_entry.c.errand_id == reservations.c.errand_id,
                    out_entry.c.kind == EntryKind.TRANSFER_OUT,
                    out_entry.c.user_id == reservations.c.requester_id,
                    out_entry.c.reserved_delta == -reservations.c.amount,
                ),
            ).outerjoin(
                in_entry,
                and_(
                    in_entry.c.errand_id == reservations.c.errand_id,
                    in_entry.c.kind == EntryKind.TRANSFER_IN,
                    in_entry.c.user_id == reservations.c.courier_id,
                    in_entry.c.available_delta == reservations.c.amount,
                ),
            )
        )
        .where(
            reservations.c.status == ReservationStatus.TRANSFERRED,
            or_(out_entry.c.id.is_(None), in_entry.c.id.is_(None)),
        )
    ):
        problems.append(f"Errand {row[0]} is TRANSFERRED but is missing a matching transfer entry")

    # 5. Holds waiting too long
    cutoff = datetime.now(UTC) - timedelta(hours=stale_hold_hours)
    stale = [
        StaleHold(errand_id=r.errand_id, requester_id=r.requester_id, amount=r.amount, held_since=r.created_at)
        for r in await conn.execute(
            select(reservations.c.errand_id, reservations.c.requester_id, reservations.c.amount, reservations.c.created_at)
            .where(reservations.c.status == ReservationStatus.HELD, reservations.c.created_at < cutoff)
            .order_by(reservations.c.created_at)
        )
    ]

    return AuditReport(
        ok=not problems,
        checked_at=datetime.now(UTC),
        wallets=totals[0],
        total_allocated=allocated,
        total_in_circulation=totals[3],
        total_available=totals[1],
        total_reserved=totals[2],
        problems=problems,
        stale_holds=stale,
    )


async def _main() -> bool:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        # REPEATABLE READ: every check sees the same snapshot, even while the worker keeps writing
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="REPEATABLE READ")
            async with conn.begin():
                report = await run_audit(conn, stale_hold_hours=settings.stale_hold_hours)
    finally:
        await engine.dispose()
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return report.ok


def main() -> None:
    sys.exit(0 if asyncio.run(_main()) else 1)
