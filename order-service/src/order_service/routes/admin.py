# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated read-only admin view of all errands, filtered by requester, courier and state; AI-added the
#        list of errands whose credits are stuck PENDING (Task 9).
# Author review: <to be completed by author>

"""Admin views. Read-only: admins can't change errands (only the requester cancels, D1)."""

from typing import Annotated

from fastapi import APIRouter, Query

from order_service.auth import AdminUser
from order_service.clients import Clients
from order_service.db import Engine
from order_service.errand_views import errand_page
from order_service.schemas import ErrandPage, ErrandSort
from order_service.states import State
from order_service.sweeper import stuck
from order_service.tables import errands

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/errands", response_model=ErrandPage, summary="All errands, e.g. one requester's or one courier's")
async def all_errands(
    engine: Engine,
    user: AdminUser,
    clients: Clients,
    requester_id: Annotated[int | None, Query(alias="requesterId", ge=1)] = None,
    courier_id: Annotated[int | None, Query(alias="courierId", ge=1)] = None,
    state: State | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: ErrandSort = ErrandSort.MOST_RECENT,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    conditions = []
    if requester_id is not None:
        conditions.append(errands.c.requester_id == requester_id)
    if courier_id is not None:
        conditions.append(errands.c.courier_id == courier_id)
    if state is not None:
        conditions.append(errands.c.state == state)
    return await errand_page(engine, clients, user, conditions, q=q, sort=sort, page=page, page_size=page_size)


# Lists errands with credits that have been pending for too long - for manual admin use
@router.get("/stuck", response_model=ErrandPage, summary="Errands whose credits have been PENDING too long")
async def stuck_errands(
    engine: Engine,
    user: AdminUser,
    clients: Clients,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    """Credits PENDING for longer than RECONCILE_AFTER_MINUTES. The sweeper resends their commands; one that stays
    here (e.g. a courier with no wallet, or the broker down) needs a person to look at it."""
    return await errand_page(
        engine, clients, user, [stuck()], q=None, sort=ErrandSort.LEAST_RECENT, page=page, page_size=page_size
    )
