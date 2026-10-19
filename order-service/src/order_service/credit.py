# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated mirror of the Credit Service's ReservationResult reply and the rule that applies a reply to its
#        errand (docs/order-service-plan.md, section 6), idempotent and never moving credits backwards.
# Author review: <to be completed by author>

"""Applying the Credit Service's replies to errands.

Every credit command gets a ReservationResult reply describing the reservation as it is now, not just the command's
effect (credit_service/commands.py). So a reply is applied by comparing states, never by counting messages:

1. Only while the errand's credits are PENDING. Every command sets PENDING when it's sent, so a duplicate, or a reply
   that arrives after the credits have settled, changes nothing.
2. Only if the reply's status is where the errand's state says the credits should end up (target_credit_status). A
   HELD reply for an errand cancelled in the meantime is ignored; the release's reply settles it.
3. For an errand that isn't finished, only if the reply's revision is the errand's reward_revision, so a reply to an
   older reward change can't undo a newer one.

The one reply that changes an errand's state: a refused reserve cancels an OPEN errand.

Anything else is logged and ignored. apply_reply never raises for a well-formed reply, so the worker can always
acknowledge it.
"""

import logging
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from order_service.schemas import CamelModel
from order_service.states import UNFINISHED, CancelReason, CreditStatus, State, target_credit_status
from order_service.tables import errands

log = logging.getLogger(__name__)

REPLY_TYPE = "ReservationResult"
# A refused reserve's reason becomes the errand's cancel reason
_RESERVE_REFUSALS = {CancelReason.INSUFFICIENT_CREDITS, CancelReason.NO_WALLET}

Outcome = Literal["applied", "cancelled", "ignored"]


class ReservationResult(CamelModel):
    """The Credit Service's reply (credit_service.commands.ReservationResult), sent as camelCase JSON.

    Extra fields are ignored and reason codes are plain strings, so a new field or rejection code from the Credit
    Service doesn't stop replies being read.
    """

    errand_id: int
    # Null when the Credit Service has no reservation for the errand
    status: Literal["HELD", "REJECTED", "TRANSFERRED", "RELEASED"] | None
    amount: int
    revision: int
    courier_id: int | None
    # Why the reservation is REJECTED or RELEASED, e.g. INSUFFICIENT_CREDITS or EXPIRED
    reason: str | None
    # Why this command changed nothing, e.g. INSUFFICIENT_CREDITS for a raised reward
    rejection: str | None


async def apply_reply(conn: AsyncConnection, reply: ReservationResult) -> Outcome:
    """Applies one reply in the caller's transaction. The worker acknowledges the message after it commits."""
    # Locked, so a transition on the same errand waits until this reply is applied (or the other way round)
    errand = (
        await conn.execute(
            select(
                errands.c.state,
                errands.c.credit_status,
                errands.c.reward_revision,
                errands.c.courier_id,
            )
            .where(errands.c.id == reply.errand_id)
            .with_for_update()
        )
    ).one_or_none()
    if errand is None:
        return _ignored(reply, "no such errand")
    if reply.status is None:
        return _ignored(reply, "the Credit Service has no reservation for it")
    if errand.credit_status != CreditStatus.PENDING:
        return _ignored(reply, f"its credits are already {errand.credit_status}")

    state = State(errand.state)
    if state in UNFINISHED and reply.revision != errand.reward_revision:
        return _ignored(reply, f"revision {reply.revision} isn't the errand's {errand.reward_revision}")

    # The reserve was refused: the errand can never be funded, so it's cancelled
    if state is State.OPEN and reply.status == CreditStatus.REJECTED and reply.reason in _RESERVE_REFUSALS:
        await _set(
            conn,
            reply.errand_id,
            state=State.CANCELLED,
            cancel_reason=reply.reason,
            cancelled_at=func.now(),
            credit_status=CreditStatus.REJECTED,
            credit_rejection=reply.rejection,
        )
        log.info("Errand %s cancelled: its credits couldn't be reserved (%s)", reply.errand_id, reply.reason)
        return "cancelled"

    if reply.status not in target_credit_status(state):
        return _ignored(reply, f"{reply.status} isn't where a {state} errand's credits should end up")
    if state is State.COMPLETED and reply.courier_id != errand.courier_id:
        return _ignored(reply, f"it paid courier {reply.courier_id}, not {errand.courier_id}")

    values = {"credit_status": reply.status, "credit_rejection": reply.rejection}
    if state in UNFINISHED:
        # HELD: the amount actually held. After a refused reward change it's the old reward, which undoes the edit.
        values["reward"] = reply.amount
    await _set(conn, reply.errand_id, **values)
    log.info("Errand %s credits %s%s", reply.errand_id, reply.status, f" ({reply.rejection})" if reply.rejection else "")
    return "applied"


async def _set(conn: AsyncConnection, errand_id: int, **values) -> None:
    await conn.execute(update(errands).where(errands.c.id == errand_id).values(**values, updated_at=func.now()))


def _ignored(reply: ReservationResult, why: str) -> Outcome:
    log.info("Ignored %s reply for errand %s: %s", reply.status, reply.errand_id, why)
    return "ignored"

