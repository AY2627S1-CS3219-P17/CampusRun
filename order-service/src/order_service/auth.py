# AI Assistance Disclosure:
# Tool: OpenAI Codex (GPT-6), date: 2026-10-17
# Scope: Validated user-service JWTs before protected autofill requests and separated expired from invalid sessions.
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: Replaced with credit-service/auth.py (integer user id, AnyUser, AdminUser); kept the raw token on
#        CurrentUser so calls to other services can be made as the signed-in user.
# Author review: <to be completed by author>

"""Identity and role checks.

The User Service signs an access token (JWT) when a user signs in. This service checks the signature with the
shared JWT_SECRET and reads two claims from it:

    sub   the user's id (string of an integer)
    role  "student" or "admin"

Missing, malformed, expired or wrongly signed token  -> 401 Unauthorized
Valid token, but the role may not do this             -> 403 Forbidden
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from order_service.config import get_settings


class Role(StrEnum):
    STUDENT = "student"
    ADMIN = "admin"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    role: Role
    # Forwarded when this service calls the Supplier, User or Credit Service for the user. Left out of repr so
    # it never ends up in a log line.
    token: str = field(repr=False)

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
        assert settings.jwt_secret is not None  # checked when the API starts
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            # Only the configured algorithm is accepted, so a token signed with "none" is rejected
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session has expired. Sign in again.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Your session is not valid. Sign in again.")

    try:
        return CurrentUser(id=int(claims["sub"]), role=Role(claims["role"]), token=token)
    except ValueError:
        raise _unauthorized("Your session is not valid. Sign in again.")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Sign in to continue.")
    return decode_token(credentials.credentials)


async def require_admin(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can see this.")
    return user


AnyUser = Annotated[CurrentUser, Depends(get_current_user)]
AdminUser = Annotated[CurrentUser, Depends(require_admin)]
