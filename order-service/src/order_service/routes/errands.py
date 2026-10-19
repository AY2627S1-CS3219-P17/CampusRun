# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated errand endpoints: create (supplier and wallet checks, a new personal delivery location if
#        needed, and the ReserveCredits command in the same transaction), Explore, and one errand by id. Calls to
#        other services happen outside the database transaction; AI-added editing an OPEN errand.
# Author review: <to be completed by author>

"""Errands at the service root: POST / creates one, GET / is Explore, GET /{id} is one errand.

Creating an errand doesn't reserve its credits directly. The errand starts OPEN with its credits PENDING, and a
ReserveCredits command goes into the outbox in the same transaction, so the command exists if and only if the errand
does (docs/order-service-plan.md, section 6). Couriers only see it once the Credit Service has reserved the credits.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import exists, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from order_service import transitions

from order_service.auth import AnyUser, CurrentUser
from order_service.clients import Clients, ServiceClients
from order_service.config import get_settings
from order_service.db import Engine
from order_service.errand_views import errand_page, errand_query, explore_for, to_out, visible_to
from order_service.errors import FieldError
from order_service.outbox import enqueue
from order_service.routes import delivery_locations as locations
from order_service.schemas import MAX_LEAD, ErrandCreate, ErrandOut, ErrandPage, ErrandSort, ErrandUpdate
from order_service.states import CreditStatus, State
from order_service.tables import delivery_locations, errands

router = APIRouter(tags=["errands"])

NOT_FOUND = "This errand does not exist."
ErrandId = Annotated[int, Path(ge=1)]


async def check_wallet(clients: ServiceClients, user: CurrentUser, needed: int) -> None:
    """Advisory: an early, clear answer for most shortfalls. The Credit Service's reserve is the real check, since two
    errands created at once can both pass this. Skipped if the Credit Service can't be reached."""
    wallet = await clients.get_wallet(user.token)
    if wallet is None:
        return
    if wallet.status != "ACTIVE":
        raise FieldError("credits", "Your credits are still being set up. Try again in a moment.")
    if wallet.available is not None and wallet.available < needed:
        raise FieldError("credits", f"You have {wallet.available} credits available.")


async def delivery_point(conn: AsyncConnection, user: CurrentUser, body: ErrandCreate | ErrandUpdate) -> int | None:
    """The delivery location id to use: a saved one the user may choose, or a new one of their own from the form.

    Runs in the caller's transaction, so a saved location can't be deactivated between this check and the insert.
    None if the body changes neither (an edit that keeps the delivery point).
    """
    if body.delivery_location_id is not None:
        usable = await conn.scalar(
            select(
                exists().where(
                    delivery_locations.c.id == body.delivery_location_id,
                    delivery_locations.c.active,
                    locations.visible_to(user),
                )
            )
        )
        if not usable:
            raise FieldError("deliveryLocationId", "Choose a delivery location from the list.")
        return body.delivery_location_id
    if body.building is None:
        return None
    # A new delivery point from the form becomes one of the requester's own locations
    return await conn.scalar(
        insert(delivery_locations)
        .values(
            name=body.building,
            floor=body.floor,
            description=body.description,
            latitude=body.latitude,
            longitude=body.longitude,
            created_by=user.id,
            updated_by=user.id,
        )
        .returning(delivery_locations.c.id)
    )


async def respond(engine: AsyncEngine, errand_id: int, clients: ServiceClients, user: CurrentUser, **kwargs) -> ErrandOut:
    """The errand as the caller now sees it, read after the transaction has committed."""
    async with engine.connect() as conn:
        row = (await conn.execute(errand_query().where(errands.c.id == errand_id))).one()
    [errand] = await to_out([row], clients, user, **kwargs)
    return errand


@router.post("/", response_model=ErrandOut, status_code=status.HTTP_201_CREATED, summary="Request an errand")
async def create_errand(body: ErrandCreate, engine: Engine, user: AnyUser, clients: Clients, response: Response):
    # Calls to other services come first, before a database connection is taken, so a slow service can't hold one.
    # 422 for an unknown or deactivated supplier, 503 if it can't be checked.
    supplier = await clients.require_active_supplier(body.supplier_id, user.token)
    await check_wallet(clients, user, body.credits)

    # One short transaction for everything in this database: committed before the response is sent
    async with engine.begin() as conn:
        location_id = await delivery_point(conn, user, body)
        errand_id = await conn.scalar(
            insert(errands)
            .values(
                requester_id=user.id,
                state=State.OPEN,
                credit_status=CreditStatus.PENDING,
                title=body.title,
                reward=body.credits,
                supplier_id=body.supplier_id,
                delivery_location_id=location_id,
                deliver_by=body.deliver_by,
            )
            .returning(errands.c.id)
        )
        # Same transaction as the errand: sent if and only if the errand is saved
        await enqueue(conn, "ReserveCredits", {"errandId": errand_id, "requesterId": user.id, "amount": body.credits})

    response.headers["Location"] = f"{get_settings().root_path}/{errand_id}"
    return await respond(engine, errand_id, clients, user, known_suppliers={supplier.id: supplier})


@router.get("/", response_model=ErrandPage, summary="Explore: errands waiting for a courier")
async def explore(
    engine: Engine,
    user: AnyUser,
    clients: Clients,
    q: Annotated[str | None, Query(max_length=100, description="Title, delivery location or supplier name.")] = None,
    sort: ErrandSort = ErrandSort.MOST_RECENT,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return await errand_page(engine, clients, user, explore_for(user), q=q, sort=sort, page=page, page_size=page_size)


@router.get("/{errand_id}", response_model=ErrandOut, summary="One errand")
async def get_errand(errand_id: ErrandId, engine: Engine, user: AnyUser, clients: Clients):
    async with engine.connect() as conn:
        row = (await conn.execute(errand_query().where(errands.c.id == errand_id, visible_to(user)))).one_or_none()
    # The same 404 whether it doesn't exist or isn't visible to you, so ids reveal nothing about other errands
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    [errand] = await to_out([row], clients, user)
    return errand


@router.patch("/{errand_id}", response_model=ErrandOut, summary="Change an errand before a courier accepts it")
async def edit_errand(errand_id: ErrandId, body: ErrandUpdate, engine: Engine, user: AnyUser, clients: Clients):
    async with engine.connect() as conn:
        current = (
            await conn.execute(
                select(errands.c.reward, errands.c.created_at).where(errands.c.id == errand_id, visible_to(user))
            )
        ).one_or_none()
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    # Edits can't keep an errand (and its reserved credits) alive past 24 hours after it was posted
    if body.deliver_by is not None and body.deliver_by > current.created_at + MAX_LEAD:
        raise FieldError("deliverBy", "Choose a time within 24 hours of when you posted the errand.")

    # Other services first, outside the transaction
    supplier = None
    if body.supplier_id is not None:
        supplier = await clients.require_active_supplier(body.supplier_id, user.token)
    if body.credits is not None and body.credits > current.reward:
        await check_wallet(clients, user, body.credits - current.reward)

    changes: dict = {}
    for field, column in (("title", "title"), ("supplier_id", "supplier_id"), ("deliver_by", "deliver_by"), ("credits", "reward")):
        if getattr(body, field) is not None:
            changes[column] = getattr(body, field)
    async with engine.begin() as conn:
        location_id = await delivery_point(conn, user, body)
        if location_id is not None:
            changes["delivery_location_id"] = location_id
        await transitions.edit(conn, errand_id, user, changes)

    return await respond(
        engine, errand_id, clients, user, known_suppliers={supplier.id: supplier} if supplier else None
    )
