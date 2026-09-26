# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated access-token check and student/admin role dependencies;
#        AI-changed it to read the account type from the "type" claim, matching the User Service (Claude Code, 2026-09-27).
# Author review: <to be completed by author>

"""Identity and role checks.

The User Service signs an access token (JWT) when a user signs in. This service
never calls the User Service per request: it checks the token's signature with the
shared JWT_SECRET and reads two claims from it:

    sub   the user's id (string)
    type  "student" or "admin"

Missing, malformed, expired or wrongly signed token  -> 401 Unauthorized
Valid token, but the role may not do this             -> 403 Forbidden
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from supplier_service.config import get_settings


class Role(StrEnum):
    STUDENT = "student"
    ADMIN = "admin"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: Role

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN


bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Access token issued by the User Service. Paste the token only, without 'Bearer'.",
)


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_token(token: str) -> CurrentUser:
    try:
        settings = get_settings()
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            # Only the configured algorithm is accepted, so a token signed with
            # "none" or another algorithm is rejected.
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session has expired. Sign in again.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Your session is not valid. Sign in again.")

    try:
        role = Role(claims.get("type"))
    except ValueError:
        raise _unauthorized("Your session is not valid. Sign in again.")
    return CurrentUser(id=claims["sub"], role=role)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Sign in to continue.")
    return decode_token(credentials.credentials)


async def require_admin(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can make this change.",
        )
    return user


AnyUser = Annotated[CurrentUser, Depends(get_current_user)]
AdminUser = Annotated[CurrentUser, Depends(require_admin)]
