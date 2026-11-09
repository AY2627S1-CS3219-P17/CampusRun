# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated access-token check and student/admin role dependencies;
#        AI-changed it to read the account type from the "type" claim, matching the User Service (Claude Code, 2026-09-27);
#        AI-renamed the claim to "role" (Claude Code, 2026-09-28).
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-switched token verification from HS256 with JWT_SECRET to RS256 with JWT_PUBLIC_KEY.
# Author review: <to be completed by author>

"""Identity and role checks.

The User Service signs an access token (JWT) with its RSA private key when a user
signs in. This service never calls the User Service per request: it checks the
token's signature with the matching public key (JWT_PUBLIC_KEY), which can verify
tokens but not create them, and reads two claims from it:

    sub   the user's id (string)
    role  "student" or "admin"

Missing, malformed, expired or wrongly signed token  -> 401 Unauthorized
Valid token, but the role may not do this             -> 403 Forbidden
"""

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Annotated

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from supplier_service.config import get_settings

# Must match ALGORITHM in user-service/security.py. Pinned, so a token can't choose "none", or HS256 with the
# public key (which every service has) as its secret.
ALGORITHM = "RS256"


@lru_cache
def _load_public_key(pem: str) -> RSAPublicKey:
    # Parsed once instead of on every request; config.py has already checked it is an RSA key
    key = load_pem_public_key(pem.encode())
    assert isinstance(key, RSAPublicKey)
    return key


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
        assert settings.jwt_public_key is not None  # checked when the API starts
        claims = jwt.decode(
            token,
            _load_public_key(settings.jwt_public_key),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session has expired. Sign in again.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Your session is not valid. Sign in again.")

    try:
        role = Role(claims["role"])
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
