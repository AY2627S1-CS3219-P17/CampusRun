# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-generated refresh-session functions (start, rotate with reuse detection, revoke), following the team's
#        choices: rotation on every refresh, 7-day sessions fixed at sign-in, and revoking every session on a
#        password change.
# Author review: <to be completed by author>

"""Refresh sessions: how a signed-in tab gets new access tokens without the password.

Sign-in starts a session and returns a refresh token. Each refresh swaps it for a new one (rotation), so a token
works once. If a token that was already swapped is presented again, someone else has a copy, and the session is
revoked, so neither copy works any more.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from user_service.security import Role
from user_service.tables import refresh_sessions, users

log = logging.getLogger(__name__)


def _new_token() -> tuple[str, bytes]:
    # 256 random bits: can't be guessed, so a plain SHA-256 is enough to store it
    token = secrets.token_urlsafe(32)
    return token, _hash(token)


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


async def start_session(conn: AsyncConnection, user_id: int, lifetime: timedelta) -> str:
    """Start a session for a successful sign-in and return its refresh token."""
    now = datetime.now(UTC)
    # Housekeeping: drop this account's sessions that can no longer be used, so the table doesn't grow forever
    await conn.execute(
        refresh_sessions.delete().where(
            refresh_sessions.c.user_id == user_id,
            or_(refresh_sessions.c.expires_at < now, refresh_sessions.c.revoked_at.is_not(None)),
        )
    )
    token, token_hash = _new_token()
    await conn.execute(
        refresh_sessions.insert().values(user_id=user_id, token_hash=token_hash, expires_at=now + lifetime)
    )
    return token


class Refused(Enum):
    # Unknown, expired or revoked: nothing to do but sign in again
    INVALID = "invalid"
    # A token that was already swapped: the session has just been revoked, and the caller must commit that
    REUSED = "reused"


@dataclass(frozen=True)
class Rotated:
    user_id: int
    # Read from the users table on every refresh, so a role change reaches the next access token
    role: Role
    refresh_token: str


async def rotate(conn: AsyncConnection, refresh_token: str) -> Rotated | Refused:
    presented = _hash(refresh_token)
    now = datetime.now(UTC)

    # FOR UPDATE: two refreshes with the same token run one after the other, so only the first can rotate it.
    # The second then finds it in previous_hash and is treated as reuse.
    row = (
        await conn.execute(
            select(refresh_sessions.c.id, refresh_sessions.c.user_id, users.c.role)
            .join(users, users.c.id == refresh_sessions.c.user_id)
            .where(
                refresh_sessions.c.token_hash == presented,
                refresh_sessions.c.revoked_at.is_(None),
                refresh_sessions.c.expires_at > now,
            )
            .with_for_update(of=refresh_sessions)
        )
    ).one_or_none()

    if row is not None:
        token, token_hash = _new_token()
        await conn.execute(
            update(refresh_sessions)
            .where(refresh_sessions.c.id == row.id)
            .values(token_hash=token_hash, previous_hash=presented, last_used_at=now)
        )
        return Rotated(user_id=row.user_id, role=row.role, refresh_token=token)

    # Only the token just before the current one is kept. An older one is simply unknown, which is still refused.
    reused = await conn.scalar(
        update(refresh_sessions)
        .where(refresh_sessions.c.previous_hash == presented, refresh_sessions.c.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(refresh_sessions.c.id)
    )
    if reused is not None:
        log.warning("Refresh token reused; revoked session %s", reused)
        return Refused.REUSED
    return Refused.INVALID


async def end_session(conn: AsyncConnection, refresh_token: str) -> None:
    """Logout. Does nothing for an unknown token, so logging out twice is harmless."""
    await conn.execute(
        update(refresh_sessions)
        .where(refresh_sessions.c.token_hash == _hash(refresh_token), refresh_sessions.c.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def end_all_sessions(conn: AsyncConnection, user_id: int) -> None:
    """Every session of the account, e.g. after a password change."""
    await conn.execute(
        update(refresh_sessions)
        .where(refresh_sessions.c.user_id == user_id, refresh_sessions.c.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
