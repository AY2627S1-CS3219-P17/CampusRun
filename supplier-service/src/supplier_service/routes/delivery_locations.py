# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-assisted review and debugging for delivery location endpoints: list/search, get, create, edit and soft delete.
# Author review: <to be completed by author>

from math import ceil
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from supplier_service.auth import AdminUser, AnyUser
from supplier_service.db import Connection
from supplier_service.routes.suppliers import like_pattern
from supplier_service.schemas import (
    DeliveryLocationCreate,
    DeliveryLocationOut,
    DeliveryLocationUpdate,
    Page,
    to_db,
)
from supplier_service.tables import delivery_locations

router = APIRouter(prefix="/delivery-locations", tags=["delivery locations"])

NOT_FOUND = "This delivery location does not exist or has been deleted."
LocationId = Annotated[int, Path(ge=1)]
not_deleted = delivery_locations.c.deleted_at.is_(None)


def _raise_for_integrity_error(exc: IntegrityError, name: str | None) -> None:
    code = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)
    if code == "23505":
        raise HTTPException(status.HTTP_409_CONFLICT, f"A delivery location named “{name}” already exists.")
    raise exc


@router.get("", response_model=Page[DeliveryLocationOut], summary="List and search delivery locations")
async def list_delivery_locations(
    conn: Connection,
    user: AnyUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    active: Annotated[bool, Query(description="false lists deactivated ones (admins only).")] = True,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
):
    if not active and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can view deactivated delivery locations.")

    conditions = [not_deleted, delivery_locations.c.active.is_(active)]
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
        await conn.execute(select(delivery_locations).where(delivery_locations.c.id == location_id, not_deleted))
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return DeliveryLocationOut.model_validate(dict(row))


@router.post(
    "", response_model=DeliveryLocationOut, status_code=status.HTTP_201_CREATED, summary="Create a delivery location (admin)"
)
async def create_delivery_location(body: DeliveryLocationCreate, conn: Connection, admin: AdminUser, response: Response):
    values = to_db(body) | {"created_by": admin.id, "updated_by": admin.id}
    try:
        row = (await conn.execute(insert(delivery_locations).values(**values).returning(delivery_locations))).mappings().one()
    except IntegrityError as exc:
        _raise_for_integrity_error(exc, body.name)
    response.headers["Location"] = f"/delivery-locations/{row['id']}"
    return DeliveryLocationOut.model_validate(dict(row))


@router.patch(
    "/{location_id}", response_model=DeliveryLocationOut, summary="Edit, deactivate or reactivate a delivery location (admin)"
)
async def update_delivery_location(location_id: LocationId, body: DeliveryLocationUpdate, conn: Connection, admin: AdminUser):
    changes = to_db(body, exclude_unset=True)
    stmt = (
        update(delivery_locations)
        .where(delivery_locations.c.id == location_id, not_deleted)
        .values(**changes, updated_by=admin.id)
        .returning(delivery_locations)
    )
    try:
        row = (await conn.execute(stmt)).mappings().first()
    except IntegrityError as exc:
        _raise_for_integrity_error(exc, changes.get("name"))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return DeliveryLocationOut.model_validate(dict(row))


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a delivery location (admin)")
async def delete_delivery_location(location_id: LocationId, conn: Connection, admin: AdminUser):
    deleted = await conn.scalar(
        update(delivery_locations)
        .where(delivery_locations.c.id == location_id, not_deleted)
        .values(deleted_at=func.now(), updated_by=admin.id)
        .returning(delivery_locations.c.id)
    )
    if deleted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
