# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-assisted review and debugging for supplier endpoints, including list/search/filter/sort/paginate, get, create,
#        edit (including activate/deactivate) and soft delete;
#        AI-removed the /suppliers prefix and made Location include ROOT_PATH (Claude Code, 2026-09-27).
# Author review: <to be completed by author>

from datetime import datetime, time
from math import ceil
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import and_, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError

from supplier_service.auth import AdminUser, AnyUser
from supplier_service.config import get_settings
from supplier_service.db import Connection
from supplier_service.errors import FORM, FieldError
from supplier_service.schemas import (
    Page,
    SupplierCreate,
    SupplierOut,
    SupplierSort,
    SupplierType,
    SupplierUpdate,
    to_db,
)
from supplier_service.tables import supplier_search_text, suppliers

# No prefix: the gateway already serves this service under /api/suppliers
router = APIRouter(tags=["suppliers"])

EARTH_RADIUS_M = 6_371_000
NOT_FOUND = "This supplier does not exist or has been deleted."

SupplierId = Annotated[int, Path(ge=1)]
not_deleted = suppliers.c.deleted_at.is_(None)


# ------------------------------------------------------------------ helpers


def campus_time_now() -> time:
    tz = ZoneInfo(get_settings().timezone)
    return datetime.now(tz).time().replace(second=0, microsecond=0)


def is_open(now: time, start: time, end: time) -> bool:
    """An end time earlier than the start time means the supplier closes after midnight."""
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def open_now_condition(now: time):
    """The same rule as is_open(), as a SQL condition."""
    s, e = suppliers.c.start_time, suppliers.c.end_time
    return or_(
        and_(s <= e, s <= now, e >= now),
        and_(s > e, or_(s <= now, e >= now)),
    )


def distance_from(lat: float, lng: float):
    """Great-circle (haversine) distance in metres from (lat, lng) to each supplier."""
    d_lat = func.radians(suppliers.c.latitude - lat)
    d_lng = func.radians(suppliers.c.longitude - lng)
    a = func.power(func.sin(d_lat / 2), 2) + func.cos(func.radians(lat)) * func.cos(
        func.radians(suppliers.c.latitude)
    ) * func.power(func.sin(d_lng / 2), 2)
    return (2 * EARTH_RADIUS_M) * func.asin(func.least(1.0, func.sqrt(a)))


def like_pattern(text: str) -> str:
    """Match `text` anywhere, treating % and _ typed by the user as ordinary characters."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def to_out(row, now: time) -> SupplierOut:
    data = dict(row)
    data["is_open_now"] = is_open(now, row["start_time"], row["end_time"])
    return SupplierOut.model_validate(data)


def raise_for_integrity_error(exc: IntegrityError, name: str | None) -> None:
    code = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)
    if code == "23505":  # unique_violation: the only unique rule is the name
        raise HTTPException(status.HTTP_409_CONFLICT, f"A supplier named “{name}” already exists.")
    if code == "23514":  # check_violation
        raise FieldError(FORM, "These details aren't valid together. Reload and try again.")
    raise exc


# ------------------------------------------------------------------- queries


@router.get("/", response_model=Page[SupplierOut], summary="List, search, filter, sort and page through suppliers")
async def list_suppliers(
    conn: Connection,
    user: AnyUser,
    q: Annotated[
        str | None,
        Query(max_length=100, description="Keyword, matched ignoring case against name, building and location description."),
    ] = None,
    supplier_type: Annotated[
        list[SupplierType] | None, Query(alias="type", description="Repeat to match any of several.")
    ] = None,
    building: Annotated[str | None, Query(max_length=100, description="Exact building name, any case.")] = None,
    open_now: Annotated[bool, Query(alias="openNow", description="Only suppliers open at the current campus time.")] = False,
    active: Annotated[bool, Query(description="false lists deactivated suppliers (admins only).")] = True,
    near_lat: Annotated[float | None, Query(alias="nearLat", ge=-90, le=90)] = None,
    near_lng: Annotated[float | None, Query(alias="nearLng", ge=-180, le=180)] = None,
    radius: Annotated[
        float | None, Query(gt=0, le=10_000, description="Metres from nearLat/nearLng.")
    ] = None,
    sort: SupplierSort = SupplierSort.NAME,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    if not active and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can view deactivated suppliers.")
    if (near_lat is None) != (near_lng is None):
        raise FieldError("nearLat", "Give both nearLat and nearLng.")
    has_point = near_lat is not None
    if radius is not None and not has_point:
        raise FieldError("radius", "A radius needs a point: add nearLat and nearLng.")
    if sort is SupplierSort.DISTANCE and not has_point:
        raise FieldError("sort", "Sorting by distance needs a point: add nearLat and nearLng.")

    now = campus_time_now()
    conditions = [not_deleted, suppliers.c.active.is_(active)]
    if q and q.strip():
        conditions.append(supplier_search_text.ilike(like_pattern(q.strip()), escape="\\"))
    if supplier_type:
        conditions.append(suppliers.c.type.in_([t.value for t in supplier_type]))
    if building and building.strip():
        conditions.append(func.lower(suppliers.c.building) == building.strip().lower())
    if open_now:
        conditions.append(open_now_condition(now))

    columns = [suppliers]
    distance = None
    if has_point:
        distance = distance_from(near_lat, near_lng)
        columns.append(distance.label("distance_m"))
        if radius is not None:
            conditions.append(distance <= radius)

    order_by = {
        SupplierSort.NAME: [func.lower(suppliers.c.name)],
        SupplierSort.NAME_DESC: [func.lower(suppliers.c.name).desc()],
        SupplierSort.TYPE: [suppliers.c.type, func.lower(suppliers.c.name)],
        SupplierSort.NEWEST: [suppliers.c.created_at.desc()],
        SupplierSort.RECENTLY_UPDATED: [suppliers.c.updated_at.desc()],
        SupplierSort.DISTANCE: [distance],
    }[sort]

    total = await conn.scalar(select(func.count()).select_from(suppliers).where(*conditions))
    rows = (
        await conn.execute(
            select(*columns)
            .where(*conditions)
            .order_by(*order_by, suppliers.c.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).mappings()

    return Page[SupplierOut](
        items=[to_out(row, now) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size),
    )


@router.get("/buildings", response_model=list[str], summary="Building names, for the location filter")
async def list_buildings(conn: Connection, user: AnyUser):
    conditions = [not_deleted]
    if not user.is_admin:
        conditions.append(suppliers.c.active.is_(True))
    # One entry per building, ignoring case ("COM2" and "com2" are the same building),
    # spelled the way the earliest-added supplier spells it. Not min(): which spelling
    # min() picks depends on the database's collation, so it differs between machines.
    same_building = func.lower(suppliers.c.building)
    first_spellings = (
        select(suppliers.c.building)
        .where(*conditions)
        .ext(distinct_on(same_building))
        .order_by(same_building, suppliers.c.id)
        .subquery()
    )
    result = await conn.scalars(
        select(first_spellings.c.building).order_by(func.lower(first_spellings.c.building))
    )
    return result.all()


@router.get("/{supplier_id}", response_model=SupplierOut, summary="Get one supplier by id")
async def get_supplier(supplier_id: SupplierId, conn: Connection, user: AnyUser):
    # Deactivated suppliers stay readable by id (active: false), so errands that
    # point at them can still show where the pickup was.
    row = (await conn.execute(select(suppliers).where(suppliers.c.id == supplier_id, not_deleted))).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return to_out(row, campus_time_now())


# ----------------------------------------------------------------- commands


@router.post("/", response_model=SupplierOut, status_code=status.HTTP_201_CREATED, summary="Create a supplier (admin)")
async def create_supplier(body: SupplierCreate, conn: Connection, admin: AdminUser, response: Response):
    values = to_db(body) | {"created_by": admin.id, "updated_by": admin.id}
    try:
        row = (await conn.execute(insert(suppliers).values(**values).returning(suppliers))).mappings().one()
    except IntegrityError as exc:
        raise_for_integrity_error(exc, body.name)
    response.headers["Location"] = f"{get_settings().root_path}/{row['id']}"
    return to_out(row, campus_time_now())


@router.patch(
    "/{supplier_id}", response_model=SupplierOut, summary="Edit, deactivate or reactivate a supplier (admin)"
)
async def update_supplier(supplier_id: SupplierId, body: SupplierUpdate, conn: Connection, admin: AdminUser):
    changes = to_db(body, exclude_unset=True)
    stmt = (
        update(suppliers)
        .where(suppliers.c.id == supplier_id, not_deleted)
        .values(**changes, updated_by=admin.id)
        .returning(suppliers)
    )
    try:
        row = (await conn.execute(stmt)).mappings().first()
    except IntegrityError as exc:
        raise_for_integrity_error(exc, changes.get("name"))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return to_out(row, campus_time_now())


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a supplier (admin)")
async def delete_supplier(supplier_id: SupplierId, conn: Connection, admin: AdminUser):
    deleted = await conn.scalar(
        update(suppliers)
        .where(suppliers.c.id == supplier_id, not_deleted)
        .values(deleted_at=func.now(), updated_by=admin.id)
        .returning(suppliers.c.id)
    )
    if deleted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
