# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for read-only endpoint for an errand's reservation and the admin consistency audit.
# Author review: <to be completed by author>

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select

from credit_service.audit import AuditReport, run_audit
from credit_service.auth import AdminUser, AnyUser
from credit_service.config import get_settings
from credit_service.db import Connection
from credit_service.schemas import ReservationResponse
from credit_service.tables import reservations

router = APIRouter(tags=["reservations"])


@router.get(
    "/reservations/{errand_id}",
    response_model=ReservationResponse,
    summary="The credits held for an errand and what happened to them",
)
async def errand_reservation(errand_id: Annotated[int, Path(gt=0)], user: AnyUser, conn: Connection):
    row = (await conn.execute(select(reservations).where(reservations.c.errand_id == errand_id))).one_or_none()
    # The same 404 whether it doesn't exist or isn't yours, so ids of other people's errands reveal nothing
    if row is None or not (user.is_admin or user.id in (row.requester_id, row.courier_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No credits are held for this errand.")
    return ReservationResponse.model_validate(row)


@router.get(
    "/admin/audit",
    response_model=AuditReport,
    tags=["admin"],
    summary="Check that balances, the ledger and reservations agree, and list stale holds",
)
async def audit(user: AdminUser, conn: Connection):
    return await run_audit(conn, stale_hold_hours=get_settings().stale_hold_hours)
