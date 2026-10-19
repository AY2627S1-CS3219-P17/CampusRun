# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated token-checking dependencies (from docs/auth-plan.md); AI-renamed the user token type from "user" to "student" (Claude Code, 2026-09-27);
#        AI-merged the admin login into the user one and switched to the "role" claim (Claude Code, 2026-09-28);
#        AI-removed require_student, since admins keep every student capability (Claude Code, 2026-09-28);
#        AI-aligned the error messages and role check with the other services' auth.py (Claude Code, 2026-10-19).
# Author review: <to be completed by author>

from dataclasses import dataclass
from typing import Annotated, get_args

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from user_service.config import Settings, get_settings
from user_service.security import Role, decode_access_token

# tokenUrl only tells Swagger where to log in; prefixing root_path makes it right both directly and behind the gateway
user_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().root_path}/auth/login", scheme_name="UserAuth"
)


@dataclass(frozen=True)
class Account:
    id: int
    role: Role


# The same messages as the other services' auth.py, so the web client shows one wording everywhere
SESSION_EXPIRED = "Your session has expired. Sign in again."
SESSION_INVALID = "Your session is not valid. Sign in again."


def credentials_error(message: str = SESSION_INVALID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _account_from_token(token: str, settings: Settings) -> Account:
    try:
        payload = decode_access_token(token, settings)
    except jwt.ExpiredSignatureError:
        raise credentials_error(SESSION_EXPIRED) from None
    except jwt.InvalidTokenError:
        raise credentials_error() from None
    # Role is only a type hint, so check the value too: a token with any other role is not a valid session
    if payload["role"] not in get_args(Role):
        raise credentials_error()
    try:
        return Account(id=int(payload["sub"]), role=payload["role"])
    except ValueError:
        raise credentials_error() from None


def _require(account: Account, expected: Role) -> Account:
    # Valid token, wrong role: authenticated but not allowed
    if account.role != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can do this.")
    return account


async def require_user(
    token: Annotated[str, Depends(user_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Account:
    # Any role: an admin can do everything a student can, so errand and credit routes use this too
    return _account_from_token(token, settings)


async def require_admin(account: Annotated[Account, Depends(require_user)]) -> Account:
    return _require(account, "admin")

# Adding one of these as an endpoint parameter makes FastAPI run its check first, which returns 401/403 before the endpoint runs; the parameter name doesn't matter.
CurrentUser = Annotated[Account, Depends(require_user)]
CurrentAdmin = Annotated[Account, Depends(require_admin)]
