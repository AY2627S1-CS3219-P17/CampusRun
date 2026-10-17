# AI Assistance Disclosure:
# Tool: OpenAI Codex (GPT-6), date: 2026-10-17
# Scope: Validated user-service JWTs before protected autofill requests and separated expired from invalid sessions.
# Author review: <to be completed by author>

from typing import Annotated

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from order_service.config import get_settings

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


def validate_token(token: str) -> str:
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session has expired. Sign in again.") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Your session is not valid. Sign in again.") from None

    if claims.get("role") not in ("student", "admin"):
        raise _unauthorized("Your session is not valid. Sign in again.")
    return token


def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> str:
    if credentials is None:
        raise _unauthorized("Sign in to continue.")
    return validate_token(credentials.credentials)


UserToken = Annotated[str, Security(require_token)]