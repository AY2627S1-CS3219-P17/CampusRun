# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-generated admin user management: search users, promote a student to admin, and step down from your own
#        admin role while another admin is left; role changes are serialized and re-check the caller's role in the
#        database (docs/admin-dashboard-plan.md).
# Author review: I tested the behaviour: searching, promoting and stepping down work, and the last admin can't step down.

"""Admin user management. Role changes reach a user's next access token on refresh (at most
JWT_ACCESS_TOKEN_TTL_SECONDS later), since /auth/refresh reads the role from this table."""

import logging
from math import ceil
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from user_service.auth import Account, CurrentAdmin
from user_service.db import Connection
from user_service.schemas import AdminUserPage, AdminUserResponse
from user_service.security import Role
from user_service.tables import users

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Any fixed number works; it only has to be the same for every role change
ROLE_CHANGE_LOCK = 3219_0001

USER_COLUMNS = (users.c.id, users.c.username, users.c.email, users.c.role)


def _like_pattern(term: str) -> str:
    # Matches the term anywhere, with % and _ taken literally
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _lock_role_changes(conn: AsyncConnection, caller: Account) -> None:
    """Runs role changes one at a time, until this transaction ends. Without it, the last two admins stepping down at
    the same moment would each see the other and both succeed, leaving no admin."""
    await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ROLE_CHANGE_LOCK})
    # The token's role can be up to JWT_ACCESS_TOKEN_TTL_SECONDS old. Without this, an admin who just stepped down
    # could use their old token to promote themselves straight back.
    role = await conn.scalar(select(users.c.role).where(users.c.id == caller.id))
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can do this.")


async def _count_admins(conn: AsyncConnection) -> int:
    return await conn.scalar(select(func.count()).select_from(users).where(users.c.role == "admin"))


@router.get("/users", summary="Search users by username or email")
async def list_users(
    admin: CurrentAdmin,
    conn: Connection,
    q: Annotated[str | None, Query(max_length=100)] = None,
    role: Role | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserPage:
    conditions = []
    if q and q.strip():
        pattern = _like_pattern(q.strip())
        conditions.append(or_(users.c.username.ilike(pattern, escape="\\"), users.c.email.ilike(pattern, escape="\\")))
    if role is not None:
        conditions.append(users.c.role == role)

    total = await conn.scalar(select(func.count()).select_from(users).where(*conditions))
    rows = await conn.execute(
        select(*USER_COLUMNS)
        .where(*conditions)
        .order_by(func.lower(users.c.username), users.c.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return AdminUserPage(
        items=[AdminUserResponse.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size),
    )


@router.post("/users/{user_id}/promote", summary="Make a student an admin")
async def promote(user_id: Annotated[int, Path(ge=1)], admin: CurrentAdmin, conn: Connection) -> AdminUserResponse:
    await _lock_role_changes(conn, admin)
    role = await conn.scalar(select(users.c.role).where(users.c.id == user_id))
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if role == "admin":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This user is already an admin.")
    row = (
        await conn.execute(
            update(users).where(users.c.id == user_id).values(role="admin").returning(*USER_COLUMNS)
        )
    ).one()
    log.info("Admin %s promoted user %s to admin", admin.id, user_id)
    return AdminUserResponse.model_validate(row, from_attributes=True)


@router.post("/me/step-down", summary="Give up your own admin role, if another admin is left")
async def step_down(admin: CurrentAdmin, conn: Connection) -> AdminUserResponse:
    await _lock_role_changes(conn, admin)
    if await _count_admins(conn) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You're the only admin. Promote someone else before stepping down.",
        )
    row = (
        await conn.execute(
            update(users).where(users.c.id == admin.id).values(role="student").returning(*USER_COLUMNS)
        )
    ).one()
    log.info("Admin %s stepped down to student", admin.id)
    return AdminUserResponse.model_validate(row, from_attributes=True)
