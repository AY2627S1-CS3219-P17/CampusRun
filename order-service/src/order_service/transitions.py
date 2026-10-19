# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated errand state transitions (accept, pick up, deliver, complete, cancel, edit): each one
#        conditional UPDATE with its credit command in the same transaction, and a clear 404/403/409 when refused;
#        AI-added a log line for every transition (Task 9).
# Author review: <to be completed by author>

"""Every change to an errand's state (docs/order-service-plan.md, section 5).

Each transition is a single `UPDATE errands SET ... WHERE id = :id AND <guard> RETURNING ...`. Postgres locks the row
for the update, so when two requests race (two couriers accepting, an accept and a cancel, a double completion), the
second waits for the first to commit, re-checks the guard against the new row, and matches nothing. There's no
read-then-write gap for another request to slip into.

When the update matches nothing, explain() reads the errand to say why: 404 if the caller can't see it, 403 if
they're the wrong party, 409 if it's in the wrong state or past its deadline.

Time guards (D2), checked in the database with its own clock:
    due   before deliver_by                  accept, pick up, deliver, cancel, edit
    live  before deliver_by + grace period   complete only, so a requester can still confirm an errand delivered
                                             just before the deadline
"""

import logging
from datetime import timedelta
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, Row, func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from order_service.auth import CurrentUser
from order_service.config import get_settings
from order_service.errand_views import visible_to
from order_service.outbox import enqueue
from order_service.states import CancelReason, CreditStatus, State
from order_service.tables import delivery_locations, errands

log = logging.getLogger(__name__)

Action = Literal["accept", "pick up", "deliver", "complete", "cancel", "edit"]

NOT_FOUND = "This errand does not exist."


def _grace() -> timedelta:
    return timedelta(minutes=get_settings().expiry_grace_minutes)


def due() -> ColumnElement[bool]:
    return errands.c.deliver_by > func.now()


def live() -> ColumnElement[bool]:
    return errands.c.deliver_by + _grace() > func.now()


async def _update(conn: AsyncConnection, errand_id: int, guard: list[ColumnElement[bool]], **values) -> Row | None:
    return (
        await conn.execute(
            update(errands)
            .where(errands.c.id == errand_id, *guard)
            .values(**values, updated_at=func.now())
            .returning(errands.c.id, errands.c.requester_id, errands.c.courier_id, errands.c.reward)
        )
    ).one_or_none()


# Who may do each action, and the state it needs
_PARTY = {
    "accept": "anyone but the requester",
    "pick up": "courier",
    "deliver": "courier",
    "complete": "requester",
    "cancel": "requester",
    "edit": "requester",
}
_FROM_STATE = {
    "accept": State.OPEN,
    "pick up": State.ACCEPTED,
    "deliver": State.PICKED_UP,
    "complete": State.DELIVERED,
    "cancel": State.OPEN,
    "edit": State.OPEN,
}
# The forward path; CANCELLED and EXPIRED end it from anywhere
_LIFECYCLE = [State.OPEN, State.ACCEPTED, State.PICKED_UP, State.DELIVERED, State.COMPLETED]
_STATE_MESSAGES = {
    State.OPEN: "This errand hasn't been accepted yet.",
    State.ACCEPTED: "This errand has already been accepted.",
    State.PICKED_UP: "This errand has already been picked up.",
    State.DELIVERED: "This errand has already been delivered.",
    State.COMPLETED: "This errand has already been completed.",
    State.CANCELLED: "This errand has been cancelled.",
    State.EXPIRED: "This errand has expired.",
}
_FORBIDDEN = {
    "accept": "You can't accept your own errand.",
    "pick up": "Only the errand's courier can do this.",
    "deliver": "Only the errand's courier can do this.",
    "complete": "Only the requester can confirm an errand is complete.",
    "cancel": "Only the requester can cancel an errand.",
    "edit": "Only the requester can change an errand.",
}


async def explain(conn: AsyncConnection, errand_id: int, user: CurrentUser, action: Action) -> HTTPException:
    """Why `action` matched no rows, read fresh after the update (which may have waited for a racing request)."""
    query = select(
        errands.c.state,
        errands.c.requester_id,
        errands.c.courier_id,
        errands.c.credit_status,
        (errands.c.deliver_by > func.now()).label("is_due"),
        (errands.c.deliver_by + _grace() > func.now()).label("is_live"),
    ).where(errands.c.id == errand_id)
    # A courier who loses a race to accept could see the errand a moment ago, but can't now (it's someone else's).
    # They're told what happened (409 "already accepted") rather than "not found". That reveals only an errand's
    # state, never its details. An errand that was never open to couriers stays "not found".
    if action != "accept":
        query = query.where(visible_to(user))
    row = (await conn.execute(query)).one_or_none()
    # The same 404 whether it doesn't exist or isn't visible to the caller
    if row is None or (action == "accept" and row.state == State.OPEN and row.credit_status != CreditStatus.HELD):
        return HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    party = _PARTY[action]
    wrong_party = (
        (party == "anyone but the requester" and row.requester_id == user.id)
        or (party == "courier" and row.courier_id != user.id)
        or (party == "requester" and row.requester_id != user.id)
    )
    if wrong_party:
        return HTTPException(status.HTTP_403_FORBIDDEN, _FORBIDDEN[action])

    current, needed = State(row.state), _FROM_STATE[action]
    if current != needed:
        if current in _LIFECYCLE and _LIFECYCLE.index(current) < _LIFECYCLE.index(needed):
            # e.g. deliver before pick up
            return HTTPException(status.HTTP_409_CONFLICT, f"This errand isn't ready to {action} yet.")
        return HTTPException(status.HTTP_409_CONFLICT, _STATE_MESSAGES[current])
    if action in ("accept", "edit") and row.credit_status != CreditStatus.HELD:
        return HTTPException(
            status.HTTP_409_CONFLICT, "This errand's credits are still being reserved. Try again in a moment."
        )
    if not (row.is_live if action == "complete" else row.is_due):
        return HTTPException(status.HTTP_409_CONFLICT, "This errand's deadline has passed.")
    # Shouldn't happen: every guard above passed now, so the errand changed between the update and this read
    return HTTPException(status.HTTP_409_CONFLICT, "This errand just changed. Refresh and try again.")


async def _or_explain(conn: AsyncConnection, row: Row | None, errand_id: int, user: CurrentUser, action: Action) -> Row:
    if row is None:
        raise await explain(conn, errand_id, user, action)
    log.info("Errand %s: %s by user %s", errand_id, action, user.id)
    return row


# ---------------------------------------------------------------- courier side


async def accept(conn: AsyncConnection, errand_id: int, user: CurrentUser) -> Row:
    """OPEN -> ACCEPTED. The caller has already checked the supplier is still active (D13)."""
    # Lock the errand first, so an errand edit can't swap its delivery location between here and the update below
    location_id = await conn.scalar(
        select(errands.c.delivery_location_id).where(errands.c.id == errand_id).with_for_update()
    )
    # This select is run only for its lock (SELECT ... FOR SHARE); the result is discarded. This is to prevent a
    # delivery location edit from interleaving with the accept errand process, which would result in accepting
    # an errand right before the delivery location is changed.
    # A share lock rather than FOR UPDATE, so accepts of different errands at the same location don't block each
    # other. Skipped if the errand doesn't exist: the update then matches nothing and explain() returns 404.
    if location_id is not None:
        await conn.execute(
            select(delivery_locations.c.id).where(delivery_locations.c.id == location_id).with_for_update(read=True)
        )
    row = await _update(
        conn,
        errand_id,
        [
            errands.c.state == State.OPEN,
            errands.c.credit_status == CreditStatus.HELD,
            errands.c.requester_id != user.id,
            due(),
        ],
        state=State.ACCEPTED,
        courier_id=user.id,
        accepted_at=func.now(),
    )
    return await _or_explain(conn, row, errand_id, user, "accept")


async def pick_up(conn: AsyncConnection, errand_id: int, user: CurrentUser) -> Row:
    """ACCEPTED -> PICKED_UP, by the courier."""
    row = await _update(
        conn,
        errand_id,
        [errands.c.state == State.ACCEPTED, errands.c.courier_id == user.id, due()],
        state=State.PICKED_UP,
        picked_up_at=func.now(),
    )
    return await _or_explain(conn, row, errand_id, user, "pick up")


async def deliver(conn: AsyncConnection, errand_id: int, user: CurrentUser) -> Row:
    """PICKED_UP -> DELIVERED, by the courier. The requester then confirms."""
    row = await _update(
        conn,
        errand_id,
        [errands.c.state == State.PICKED_UP, errands.c.courier_id == user.id, due()],
        state=State.DELIVERED,
        delivered_at=func.now(),
    )
    return await _or_explain(conn, row, errand_id, user, "deliver")


# -------------------------------------------------------------- requester side


async def complete(conn: AsyncConnection, errand_id: int, user: CurrentUser) -> Row:
    """DELIVERED -> COMPLETED, by the requester: the courier is paid (TransferCredits)."""
    row = await _update(
        conn,
        errand_id,
        [errands.c.state == State.DELIVERED, errands.c.requester_id == user.id, live()],
        state=State.COMPLETED,
        completed_at=func.now(),
        credit_status=CreditStatus.PENDING,
        credit_rejection=None,
    )
    row = await _or_explain(conn, row, errand_id, user, "complete")
    await enqueue(
        conn, "TransferCredits", {"errandId": row.id, "requesterId": row.requester_id, "courierId": row.courier_id}
    )
    return row


async def cancel(conn: AsyncConnection, errand_id: int, user: CurrentUser) -> Row:
    """OPEN -> CANCELLED, by the requester only (D1): the reserved credits are returned (ReleaseCredits).

    Allowed while the credits are still being reserved: the release follows the reserve in outbox order, and the
    Credit Service handles a release that arrives first.
    """
    row = await _update(
        conn,
        errand_id,
        [errands.c.state == State.OPEN, errands.c.requester_id == user.id, due()],
        state=State.CANCELLED,
        cancel_reason=CancelReason.REQUESTER,
        cancelled_at=func.now(),
        credit_status=CreditStatus.PENDING,
        credit_rejection=None,
    )
    row = await _or_explain(conn, row, errand_id, user, "cancel")
    await enqueue(conn, "ReleaseCredits", {"errandId": row.id, "requesterId": row.requester_id, "reason": "CANCELLED"})
    return row


async def edit(conn: AsyncConnection, errand_id: int, user: CurrentUser, changes: dict[str, Any]) -> Row:
    """Changes an OPEN errand before a courier accepts it (D10). A new reward is re-reserved (AdjustReservation).

    `changes` holds column values. A changed `reward` raises the revision, so a late reply to an older change is
    ignored, and sets the credits PENDING until the Credit Service answers. Refused while the credits are still being
    reserved, so the reward never changes under a pending reply.
    """
    values = dict(changes)
    # check if the reward update actually changes the value, if it doesn't, avoid all the unnecessary steps below
    if "reward" in values:
        # Locked, so the comparison and the update see the same reward
        current = await conn.scalar(select(errands.c.reward).where(errands.c.id == errand_id).with_for_update())
        if current == values["reward"]:
            del values["reward"]
    adjusting = "reward" in values
    if adjusting:
        values["reward_revision"] = errands.c.reward_revision + 1
        values["credit_status"] = CreditStatus.PENDING
        values["credit_rejection"] = None
    row = (
        await conn.execute(
            update(errands)
            .where(
                errands.c.id == errand_id,
                errands.c.state == State.OPEN,
                errands.c.requester_id == user.id,
                errands.c.credit_status == CreditStatus.HELD,
                due(),
            )
            .values(**values, updated_at=func.now())
            .returning(errands.c.id, errands.c.requester_id, errands.c.reward, errands.c.reward_revision)
        )
    ).one_or_none()
    row = await _or_explain(conn, row, errand_id, user, "edit")
    if adjusting:
        await enqueue(
            conn,
            "AdjustReservation",
            {"errandId": row.id, "requesterId": row.requester_id, "amount": row.reward, "revision": row.reward_revision},
        )
    return row
