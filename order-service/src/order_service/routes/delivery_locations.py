# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: Delivery location endpoints copied from supplier-service/routes/delivery_locations.py (AI-assisted, Claude,
#        claude.ai chat, 2026-09-26), changed so students can add their own locations, only the owner (or an admin,
#        for predefined ones) can edit, and nothing can be edited while a courier is on the way to it.
# Author review: <to be completed by author>

"""Delivery locations: where errands are delivered.

    predefined  the shared campus list (seeded, or added by an admin). Everyone sees them; only admins edit them.
    personal    added by a student, usually from the create-request form. Only that student sees and edits them.

Edits apply to every errand that uses the location (docs/order-service-plan.md, D6), so a location can't be changed
while an errand using it is in progress: the courier would be sent somewhere else on the way.
"""

from math import ceil
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import ColumnElement, and_, exists, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from order_service.auth import AnyUser, CurrentUser
from order_service.config import get_settings
from order_service.db import Connection
from order_service.schemas import DeliveryLocationCreate, DeliveryLocationOut, DeliveryLocationUpdate, Page
from order_service.states import IN_PROGRESS
from order_service.tables import delivery_locations, errands

router = APIRouter(prefix="/delivery-locations", tags=["delivery locations"])

NOT_FOUND = "This delivery location does not exist."
LocationId = Annotated[int, Path(ge=1)]


def like_pattern(text: str) -> str:
    """Match `text` anywhere, treating % and _ typed by the user as ordinary characters."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def visible_to(user: CurrentUser) -> ColumnElement[bool]:
    # The same rule for admins: they manage the predefined list, not students' own locations
    return or_(delivery_locations.c.predefined, delivery_locations.c.created_by == user.id)


def _raise_for_integrity_error(exc: IntegrityError, name: str | None) -> None:
    code = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)
    if code == "23505":
        raise HTTPException(status.HTTP_409_CONFLICT, f"A predefined delivery location named “{name}” already exists.")
    raise exc


@router.get("", response_model=Page[DeliveryLocationOut], summary="List and search delivery locations")
async def list_delivery_locations(
    conn: Connection,
    user: AnyUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    predefined: Annotated[
        bool | None, Query(description="true: only the shared campus list. false: only your own. Omit for both.")
    ] = None,
    active: Annotated[bool, Query(description="false lists deactivated ones.")] = True,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
):
    conditions = [visible_to(user), delivery_locations.c.active.is_(active)]
    if predefined is not None:
        conditions.append(delivery_locations.c.predefined.is_(predefined))
    if q and q.strip():
        pattern = like_pattern(q.strip())
        conditions.append(
            or_(
                delivery_locations.c.name.ilike(pattern, escape="\\"),
                delivery_locations.c.description.ilike(pattern, escape="\\"),
            )
        )

    total = await conn.scalar(select(func.count()).select_from(delivery_locations).where(*conditions))
    rows = (
        await conn.execute(
            select(delivery_locations)
            .where(*conditions)
            .order_by(func.lower(delivery_locations.c.name), delivery_locations.c.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).mappings()
    return Page[DeliveryLocationOut](
        items=[DeliveryLocationOut.model_validate(dict(r)) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size),
    )


@router.get("/{location_id}", response_model=DeliveryLocationOut, summary="Get one delivery location")
async def get_delivery_location(location_id: LocationId, conn: Connection, user: AnyUser):
    row = (
        (
            await conn.execute(
                select(delivery_locations).where(delivery_locations.c.id == location_id, visible_to(user))
            )
        )
        .mappings()
        .first()
    )
    # The same 404 whether it doesn't exist or is someone else's, so ids reveal nothing about other students
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return DeliveryLocationOut.model_validate(dict(row))


@router.post(
    "",
    response_model=DeliveryLocationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a delivery location (your own, or a predefined one as an admin)",
)
async def create_delivery_location(
    body: DeliveryLocationCreate,
    conn: Connection,
    user: AnyUser,
    response: Response,
):
    if body.predefined and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can add predefined delivery locations.")
    values = body.model_dump() | {"created_by": user.id, "updated_by": user.id}
    try:
        row = (await conn.execute(insert(delivery_locations).values(**values).returning(delivery_locations))).mappings().one()
    except IntegrityError as exc:
        _raise_for_integrity_error(exc, body.name)
    response.headers["Location"] = f"{get_settings().root_path}/delivery-locations/{row['id']}"
    return DeliveryLocationOut.model_validate(dict(row))


@router.patch(
    "/{location_id}",
    response_model=DeliveryLocationOut,
    summary="Edit, deactivate or reactivate a delivery location",
)
async def update_delivery_location(
    location_id: LocationId, body: DeliveryLocationUpdate, conn: Connection, user: AnyUser
):
    # Lock the location first. An accept takes a share lock on its errand's location (Task 7), so it can't slip in
    # between the in-use check below and the update. The check is its own statement, so it sees any accept that
    # committed while this one waited for the lock.
    row = (
        await conn.execute(
            select(delivery_locations.c.predefined)
            .where(delivery_locations.c.id == location_id, visible_to(user))
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if row.predefined and not user.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only administrators can change a predefined delivery location."
        )

    in_use = await conn.scalar(
        select(
            exists().where(
                and_(errands.c.delivery_location_id == location_id, errands.c.state.in_([*IN_PROGRESS]))
            )
        )
    )
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A courier is on the way to this location, so it can't be changed until their errand ends.",
        )

    changes = body.model_dump(exclude_unset=True)
    try:
        updated = (
            (
                await conn.execute(
                    update(delivery_locations)
                    .where(delivery_locations.c.id == location_id)
                    .values(**changes, updated_by=user.id)
                    .returning(delivery_locations)
                )
            )
            .mappings()
            .one()
        )
    except IntegrityError as exc:
        _raise_for_integrity_error(exc, changes.get("name"))
    return DeliveryLocationOut.model_validate(dict(updated))
