# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for read-only endpoints for the signed-in user's wallet and credit history.
# Author review: <to be completed by author>

"""The signed-in user's own wallet (F14.2). Read-only: no HTTP request can change a balance (F14.1.1)."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from credit_service.auth import AnyUser
from credit_service.db import Connection
from credit_service.schemas import LedgerEntryResponse, LedgerPage, WalletResponse, WalletStatus
from credit_service.tables import ledger_entries, wallets

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.get("/me", response_model=WalletResponse, summary="Your available and reserved credits")
async def my_wallet(user: AnyUser, conn: Connection):
    row = (
        await conn.execute(
            select(wallets.c.available, wallets.c.reserved, wallets.c.total, wallets.c.updated_at).where(
                wallets.c.user_id == user.id
            )
        )
    ).one_or_none()
    if row is None:
        # Not a 404: the account exists and its wallet is being opened (the OpenWallet message is in flight),
        # so the web client shows "pending" instead of an error
        return WalletResponse(user_id=user.id, status=WalletStatus.PENDING, available=None, reserved=None, total=None, updated_at=None)
    return WalletResponse(user_id=user.id, status=WalletStatus.ACTIVE, **row._mapping)


@router.get("/me/transactions", response_model=LedgerPage, summary="Your credit history, newest first")
async def my_transactions(
    user: AnyUser,
    conn: Connection,
    errand_id: Annotated[int | None, Query(alias="errandId", gt=0, description="Only this errand's entries")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = (
        select(
            ledger_entries.c.id,
            ledger_entries.c.errand_id,
            ledger_entries.c.kind,
            ledger_entries.c.available_delta.label("available_change"),
            ledger_entries.c.reserved_delta.label("reserved_change"),
            ledger_entries.c.available_after,
            ledger_entries.c.reserved_after,
            ledger_entries.c.created_at,
        )
        .where(ledger_entries.c.user_id == user.id)
        .order_by(ledger_entries.c.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if errand_id is not None:
        query = query.where(ledger_entries.c.errand_id == errand_id)
    rows = await conn.execute(query)
    return LedgerPage(items=[LedgerEntryResponse.model_validate(r) for r in rows], limit=limit, offset=offset)
