# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated shared errand queries and responses: who can see an errand, the Explore and tab filters,
#        search across title, delivery location and supplier name, sorting and paging, and adding the live
#        supplier details and usernames to each errand; expiresAt adds the grace period only once delivered.
# Author review: <to be completed by author>

"""Reading errands, shared by the errand, My Requests/My Tasks and admin routes."""

import asyncio
from collections.abc import Sequence
from datetime import timedelta
from math import ceil

from sqlalchemy import ColumnElement, Row, Select, and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.auth import CurrentUser
from order_service.clients import ServiceClients
from order_service.config import get_settings
from order_service.routes.delivery_locations import like_pattern
from order_service.schemas import (
    ErrandLocation,
    ErrandOut,
    ErrandPage,
    ErrandSort,
    ErrandTab,
    SupplierSummary,
)
from order_service.states import FINISHED, UNFINISHED, CreditStatus, State
from order_service.tables import delivery_locations, errands

TAB_STATES: dict[ErrandTab, frozenset[State]] = {
    ErrandTab.ACTIVE: UNFINISHED,
    ErrandTab.COMPLETED: frozenset({State.COMPLETED}),
    ErrandTab.INACTIVE: FINISHED - {State.COMPLETED},
}

# Newest first by default; ties are broken by id so pages never overlap
ORDERINGS = {
    ErrandSort.MOST_RECENT: (errands.c.created_at.desc(), errands.c.id.desc()),
    ErrandSort.LEAST_RECENT: (errands.c.created_at.asc(), errands.c.id.asc()),
    ErrandSort.MOST_CREDITS: (errands.c.reward.desc(), errands.c.created_at.desc(), errands.c.id.desc()),
    ErrandSort.LEAST_CREDITS: (errands.c.reward.asc(), errands.c.created_at.desc(), errands.c.id.desc()),
}

_JOIN = errands.join(delivery_locations, errands.c.delivery_location_id == delivery_locations.c.id)


def errand_query() -> Select:
    """Errands with their delivery location, which lives in this database."""
    return select(
        errands,
        delivery_locations.c.name.label("location_name"),
        delivery_locations.c.floor.label("location_floor"),
        delivery_locations.c.description.label("location_description"),
        delivery_locations.c.latitude.label("location_latitude"),
        delivery_locations.c.longitude.label("location_longitude"),
        delivery_locations.c.predefined.label("location_predefined"),
    ).select_from(_JOIN)


def in_explore() -> ColumnElement[bool]:
    """Open to couriers: OPEN, its credits reserved, and its deadline not yet passed."""
    return and_(
        errands.c.state == State.OPEN,
        errands.c.credit_status == CreditStatus.HELD,
        errands.c.deliver_by > func.now(),
    )


def explore_for(user: CurrentUser) -> list[ColumnElement[bool]]:
    # A requester never sees their own errands in Explore; they're in My Requests
    return [in_explore(), errands.c.requester_id != user.id]


def visible_to(user: CurrentUser) -> ColumnElement[bool]:
    """Who can see one errand: its requester and courier, admins, and anyone while it's in Explore."""
    if user.is_admin:
        return true()
    return or_(errands.c.requester_id == user.id, errands.c.courier_id == user.id, in_explore())


def in_tab(tab: ErrandTab) -> ColumnElement[bool]:
    return errands.c.state.in_(sorted(TAB_STATES[tab]))


async def _search(q: str, clients: ServiceClients, user: CurrentUser) -> tuple[ColumnElement[bool], bool]:
    """Matches title, delivery location name or supplier name. Also says whether supplier names were searched."""
    pattern = like_pattern(q)
    matches = [
        errands.c.title.ilike(pattern, escape="\\"),
        delivery_locations.c.name.ilike(pattern, escape="\\"),
    ]
    # Supplier names live in the Supplier Service (D6), so ask it which suppliers match (D12)
    supplier_ids = await clients.search_supplier_ids(q, user.token)
    if supplier_ids:
        matches.append(errands.c.supplier_id.in_(sorted(supplier_ids)))
    return or_(*matches), supplier_ids is not None


async def errand_page(
    engine: AsyncEngine,
    clients: ServiceClients,
    user: CurrentUser,
    conditions: Sequence[ColumnElement[bool]],
    *,
    q: str | None,
    sort: ErrandSort,
    page: int,
    page_size: int,
) -> ErrandPage:
    conditions = list(conditions)
    supplier_search = True
    # Calls to other services happen before and after the query, never while a database connection is held
    if q and q.strip():
        matches, supplier_search = await _search(q.strip(), clients, user)
        conditions.append(matches)

    async with engine.connect() as conn:
        total = await conn.scalar(select(func.count()).select_from(_JOIN).where(*conditions))
        rows = (
            await conn.execute(
                errand_query()
                .where(*conditions)
                .order_by(*ORDERINGS[sort])
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()
    return ErrandPage(
        items=await to_out(rows, clients, user),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size),
        supplier_search=supplier_search,
    )


async def to_out(
    rows: Sequence[Row],
    clients: ServiceClients,
    user: CurrentUser,
    *,
    known_suppliers: dict[int, SupplierSummary] | None = None,
) -> list[ErrandOut]:
    """Adds the live supplier details and usernames, fetched for the whole page at once (one call each)."""
    if not rows:
        return []
    supplier_ids = {r.supplier_id for r in rows} - set(known_suppliers or {})
    user_ids = {r.requester_id for r in rows} | {r.courier_id for r in rows if r.courier_id is not None}
    suppliers, names = await asyncio.gather(
        clients.get_suppliers(supplier_ids, user.token), clients.get_usernames(user_ids, user.token)
    )
    suppliers = (suppliers or {}) | (known_suppliers or {})
    names = names or {}
    grace = timedelta(minutes=get_settings().expiry_grace_minutes)
    return [
        ErrandOut(
            id=r.id,
            title=r.title,
            state=r.state,
            credit_status=r.credit_status,
            credit_rejection=r.credit_rejection,
            credits=r.reward,
            requester_id=r.requester_id,
            requester_name=names.get(r.requester_id),
            courier_id=r.courier_id,
            courier_name=names.get(r.courier_id) if r.courier_id is not None else None,
            supplier_id=r.supplier_id,
            supplier=suppliers.get(r.supplier_id),
            delivery_location=ErrandLocation(
                id=r.delivery_location_id,
                name=r.location_name,
                floor=r.location_floor,
                description=r.location_description,
                latitude=r.location_latitude,
                longitude=r.location_longitude,
                predefined=r.location_predefined,
            ),
            deliver_by=r.deliver_by,
            # Once delivered, the requester has the grace period to confirm (D2); this stays true after it ends
            expires_at=r.deliver_by + grace if r.delivered_at is not None else r.deliver_by,
            cancel_reason=r.cancel_reason,
            created_at=r.created_at,
            updated_at=r.updated_at,
            accepted_at=r.accepted_at,
            picked_up_at=r.picked_up_at,
            delivered_at=r.delivered_at,
            completed_at=r.completed_at,
            cancelled_at=r.cancelled_at,
            expired_at=r.expired_at,
        )
        for r in rows
    ]
