# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated shared Argon2 password hasher (pwdlib); AI-renamed the user token type from "user" to "student" (Claude Code, 2026-09-27).
# Author review: reviewed by Nathan

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from user_service.config import Settings

# Argon2id with pwdlib's recommended parameters; shared so every account type hashes the same way
password_hash = PasswordHash.recommended()

ALGORITHM = "HS256"

AccountType = Literal["student", "admin"]

# Verified against when the account doesn't exist, so a failed login takes the same time
DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


def create_access_token(account_id: int, account_type: AccountType, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        # PyJWT requires "sub" to be a string
        "sub": str(account_id),
        "type": account_type,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_ttl),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    # Raises jwt.InvalidTokenError (bad signature, expired, malformed, missing claims)
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        # Pinning the algorithm stops a forged token from choosing "none"
        algorithms=[ALGORITHM],
        options={"require": ["sub", "type", "exp"]},
    )