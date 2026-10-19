# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated errand action endpoints (accept, pick up, deliver, complete, cancel), each one short transaction
#        around a transition, with the supplier check before an accept.
# Author review: <to be completed by author>

"""POST /{id}/accept | pickup | deliver | complete | cancel. Each returns the updated errand.

The rules for each action are in transitions.py; refusals are 404 (can't see it), 403 (wrong party) or 409 (wrong
state, or past its deadline).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from order_service import transitions
from order_service.auth import AnyUser, CurrentUser
from order_service.clients import Clients, ServiceClients
from order_service.db import Engine
from order_service.routes.errands import NOT_FOUND, respond
from order_service.schemas import ErrandOut
from order_service.states import CreditStatus, State
from order_service.tables import errands

log = logging.getLogger(__name__)

router = APIRouter(tags=["errand actions"])

ErrandId = Annotated[int, Path(ge=1)]
Transition = Callable[[AsyncConnection, int, CurrentUser], Awaitable[Row]]


async def _run(
    transition: Transition, errand_id: int, engine: AsyncEngine, user: CurrentUser, clients: ServiceClients
) -> ErrandOut:
    # One short transaction; the credit command (if any) is written in it too
    async with engine.begin() as conn:
        await transition(conn, errand_id, user)
    return await respond(engine, errand_id, clients, user)


@router.post("/{errand_id}/accept", response_model=ErrandOut, summary="Accept an errand as its courier")
async def accept(errand_id: ErrandId, engine: Engine, user: AnyUser, clients: Clients):
    async with engine.connect() as conn:
        errand = (
            await conn.execute(
                select(errands.c.supplier_id, errands.c.state, errands.c.credit_status).where(errands.c.id == errand_id)
            )
        ).one_or_none()
    if errand is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    # D13: no courier takes an errand whose supplier has been deactivated. Checked before the transaction, so the
    # call never holds a database connection, and only when the accept could succeed (otherwise the transition
    # below explains why it can't).
    if errand.state == State.OPEN and errand.credit_status == CreditStatus.HELD:
        suppliers = await clients.get_suppliers({errand.supplier_id}, user.token)
        if suppliers is None:
            # Deactivation is rare, so an outage doesn't block every accept; the requester can still cancel
            log.warning(
                "Accepting errand %d without checking supplier %d: supplier-service is unavailable",
                errand_id,
                errand.supplier_id,
            )
        elif errand.supplier_id not in suppliers or not suppliers[errand.supplier_id].active:
            raise HTTPException(status.HTTP_409_CONFLICT, "This supplier is no longer available.")

    return await _run(transitions.accept, errand_id, engine, user, clients)


@router.post("/{errand_id}/pickup", response_model=ErrandOut, summary="Mark the items as picked up (courier)")
async def pick_up(errand_id: ErrandId, engine: Engine, user: AnyUser, clients: Clients):
    return await _run(transitions.pick_up, errand_id, engine, user, clients)


@router.post("/{errand_id}/deliver", response_model=ErrandOut, summary="Mark the errand as delivered (courier)")
async def deliver(errand_id: ErrandId, engine: Engine, user: AnyUser, clients: Clients):
    return await _run(transitions.deliver, errand_id, engine, user, clients)


@router.post("/{errand_id}/complete", response_model=ErrandOut, summary="Confirm delivery and pay the courier (requester)")
async def complete(errand_id: ErrandId, engine: Engine, user: AnyUser, clients: Clients):
    return await _run(transitions.complete, errand_id, engine, user, clients)


@router.post("/{errand_id}/cancel", response_model=ErrandOut, summary="Cancel an errand before it's accepted (requester)")
async def cancel(errand_id: ErrandId, engine: Engine, user: AnyUser, clients: Clients):
    return await _run(transitions.cancel, errand_id, engine, user, clients)
