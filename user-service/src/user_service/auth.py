from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from user_service.config import Settings, get_settings
from user_service.security import AccountType, decode_access_token

# Two schemes so Swagger's Authorize dialog offers both logins; both read the same Bearer header.
# scheme_name must differ, or the two collide in the OpenAPI schema.
# tokenUrl only tells Swagger where to log in; prefixing root_path makes it right both directly and behind the gateway
user_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().root_path}/auth/login", scheme_name="UserAuth"
)
admin_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().root_path}/auth/admin/login", scheme_name="AdminAuth"
)


@dataclass(frozen=True)
class Account:
    id: int
    type: AccountType


def credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _account_from_token(token: str, settings: Settings) -> Account:
    try:
        payload = decode_access_token(token, settings)
    except jwt.InvalidTokenError:
        raise credentials_error() from None
    return Account(id=int(payload["sub"]), type=payload["type"])


def _require(account: Account, expected: AccountType) -> Account:
    # Valid token, wrong kind of account: authenticated but not allowed
    if account.type != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return account


async def require_user(
    token: Annotated[str, Depends(user_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Account:
    return _require(_account_from_token(token, settings), "user")


async def require_admin(
    token: Annotated[str, Depends(admin_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Account:
    return _require(_account_from_token(token, settings), "admin")


CurrentUser = Annotated[Account, Depends(require_user)]
CurrentAdmin = Annotated[Account, Depends(require_admin)]