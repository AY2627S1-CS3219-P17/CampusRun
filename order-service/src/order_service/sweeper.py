# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated sweeper for order-worker: expiring errands past their deadline with ReleaseCredits, and the
#        reconciler that resends the credit command for errands whose credits have been PENDING too long.
# Author review: <to be completed by author>

"""The background sweeper (docs/order-service-plan.md, section 6). Not a cronjob: an asyncio loop in order-worker.

Every SWEEP_SECONDS it runs:
    expire_due()  errands not yet delivered expire at deliver_by, DELIVERED ones at deliver_by + grace period (D2),
                  each with ReleaseCredits(EXPIRED) in the same transaction
    reconcile()   errands whose credits have been PENDING for RECONCILE_AFTER_MINUTES get the command for where their
                  credits should end up sent again. Safe because every credit command is idempotent; it covers a lost
                  reply, a reply the consumer had to drop, and a transfer to a courier with no wallet yet.

Each batch is one UPDATE whose rows are picked with FOR UPDATE SKIP LOCKED, so several order-worker copies never
handle the same errand, and an errand a request is changing right now is left for the next sweep. Correctness doesn't
depend on the sweeper's timing: every transition checks the deadline itself, so a late sweep only delays the refund.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import ColumnElement, Row, and_, exists, func, not_, or_, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.config import get_settings
from order_service.outbox import enqueue
from order_service.states import UNFINISHED, CreditStatus, State
from order_service.tables import errands, outbox
from order_service.transitions import due, live

log = logging.getLogger(__name__)

BATCH_SIZE = 100


def expiry_due() -> ColumnElement[bool]:
    """SQL condition that checks whether an errand should expire now: an OPEN, ACCEPTED or PICKED_UP errand past
    deliver_by, or a DELIVERED errand past deliver_by plus the grace period."""
    return or_(
        and_(errands.c.state.in_([State.OPEN, State.ACCEPTED, State.PICKED_UP]), not_(due())),
        and_(errands.c.state == State.DELIVERED, not_(live())),
    )


def stuck() -> ColumnElement[bool]:
    """Credits PENDING for longer than a reply should take. Also listed by GET /admin/stuck."""
    waited = timedelta(minutes=get_settings().reconcile_after_minutes)
    return and_(errands.c.credit_status == CreditStatus.PENDING, errands.c.updated_at <= func.now() - waited)


def awaiting_publish() -> ColumnElement[bool]:
    """A command for the errand is still in the outbox. Resending then would only add a duplicate behind it."""
    return exists().where(
        outbox.c.published_at.is_(None), outbox.c.payload["errandId"].as_integer() == errands.c.id
    )


async def expire_due(engine: AsyncEngine, *, batch_size: int = BATCH_SIZE) -> int:
    """Expires every errand past its deadline. Returns how many."""
    total = 0
    while True:
        async with engine.begin() as conn:
            picked = (
                select(errands.c.id)
                .where(expiry_due())
                .order_by(errands.c.deliver_by)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
                .cte("picked")
            )
            rows = (
                await conn.execute(
                    update(errands)
                    # The guard again: the row may have changed since it was picked
                    .where(errands.c.id == picked.c.id, expiry_due())
                    .values(
                        state=State.EXPIRED,
                        expired_at=func.now(),
                        credit_status=CreditStatus.PENDING,
                        credit_rejection=None,
                        updated_at=func.now(),
                    )
                    .returning(errands.c.id, errands.c.requester_id)
                )
            ).all()
            for row in rows:
                await enqueue(
                    conn, "ReleaseCredits", {"errandId": row.id, "requesterId": row.requester_id, "reason": "EXPIRED"}
                )
                log.info("Errand %s expired; returning its credits", row.id)
        total += len(rows)
        if len(rows) < batch_size:
            return total


def command_for(row: Row) -> tuple[str, dict[str, Any]]:
    """Takes an errand whose credits are stuck PENDING and works out which credit command to send again."""
    base = {"errandId": row.id, "requesterId": row.requester_id}
    state = State(row.state)
    if state in UNFINISHED:
        if row.reward_revision == 0:
            return "ReserveCredits", base | {"amount": row.reward}
        return "AdjustReservation", base | {"amount": row.reward, "revision": row.reward_revision}
    if state is State.COMPLETED:
        return "TransferCredits", base | {"courierId": row.courier_id}
    return "ReleaseCredits", base | {"reason": "CANCELLED" if state is State.CANCELLED else "EXPIRED"}


async def reconcile(engine: AsyncEngine, *, batch_size: int = BATCH_SIZE) -> int:
    """Resends the credit command for errands stuck PENDING. Returns how many were resent."""
    total = 0
    while True:
        async with engine.begin() as conn:
            picked = (
                select(errands.c.id)
                .where(stuck(), not_(awaiting_publish()))
                .order_by(errands.c.updated_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
                .cte("picked")
            )
            rows = (
                await conn.execute(
                    update(errands)
                    .where(errands.c.id == picked.c.id, stuck())
                    # Restarts the wait, so the command isn't resent again on the next sweep
                    .values(updated_at=func.now())
                    .returning(
                        errands.c.id,
                        errands.c.state,
                        errands.c.requester_id,
                        errands.c.courier_id,
                        errands.c.reward,
                        errands.c.reward_revision,
                    )
                )
            ).all()
            for row in rows:
                command, payload = command_for(row)
                await enqueue(conn, command, payload)
                log.warning("Errand %s credits still PENDING; resending %s", row.id, command)
        total += len(rows)
        if len(rows) < batch_size:
            return total


class Sweeper:
    """Runs in order-worker: expire, then reconcile, every interval seconds.

    Expiring first means an errand expired in this sweep has a fresh updated_at, so it isn't also sent a stale
    ReserveCredits by the reconcile straight after.
    """

    def __init__(self, engine: AsyncEngine, interval: float):
        self.engine = engine
        self.interval = interval

    async def run(self) -> None:
        while True:
            try:
                await expire_due(self.engine)
                await reconcile(self.engine)
            except (OSError, DBAPIError) as exc:
                # e.g. the database is restarting; the next sweep catches up
                log.warning("Sweep failed (%s); retrying in %.0fs", type(exc).__name__, self.interval)
            except Exception:
                log.exception("Sweep failed; retrying in %.0fs", self.interval)
            await asyncio.sleep(self.interval)
