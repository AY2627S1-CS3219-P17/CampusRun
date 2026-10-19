# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated My Requests and My Tasks endpoints: the signed-in user's errands as requester or courier,
#        by tab, with search, sorting and paging.
# Author review: <to be completed by author>

"""The signed-in user's own errands. The same student can be a requester on some errands and a courier on others."""

from typing import Annotated

from fastapi import APIRouter, Query

from order_service.auth import AnyUser
from order_service.clients import Clients
from order_service.db import Engine
from order_service.errand_views import errand_page, in_tab
from order_service.schemas import ErrandPage, ErrandSort, ErrandTab
from order_service.tables import errands

router = APIRouter(prefix="/me", tags=["my errands"])

Search = Annotated[str | None, Query(max_length=100, description="Title, delivery location or supplier name.")]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=1, le=100)]


@router.get("/requests", response_model=ErrandPage, summary="My Requests: errands you asked for")
async def my_requests(
    engine: Engine,
    user: AnyUser,
    clients: Clients,
    tab: ErrandTab = ErrandTab.ACTIVE,
    q: Search = None,
    sort: ErrandSort = ErrandSort.MOST_RECENT,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    conditions = [errands.c.requester_id == user.id, in_tab(tab)]
    return await errand_page(engine, clients, user, conditions, q=q, sort=sort, page=page, page_size=page_size)


@router.get("/tasks", response_model=ErrandPage, summary="My Tasks: errands you're delivering")
async def my_tasks(
    engine: Engine,
    user: AnyUser,
    clients: Clients,
    tab: ErrandTab = ErrandTab.ACTIVE,
    q: Search = None,
    sort: ErrandSort = ErrandSort.MOST_RECENT,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    conditions = [errands.c.courier_id == user.id, in_tab(tab)]
    return await errand_page(engine, clients, user, conditions, q=q, sort=sort, page=page, page_size=page_size)
