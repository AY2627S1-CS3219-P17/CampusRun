# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated shared Argon2 password hasher (pwdlib); AI-renamed the user token type from "user" to "student" (Claude Code, 2026-09-27);
#        AI-renamed the "type" claim to "role" (Claude Code, 2026-09-28);
#        AI-switched token signing from HS256 with a shared secret to RS256 with JWT_PRIVATE_KEY (Claude Code, 2026-11-09).
# Author review: <to be completed by author>

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pwdlib import PasswordHash

from user_service.config import Settings

# Argon2id with pwdlib's recommended parameters; shared so every account hashes the same way
password_hash = PasswordHash.recommended()

# Asymmetric: only this service holds the private key and can sign; the other services get the public key, which
# can verify tokens but not create them. Must match ALGORITHM in the other services' auth.py.
ALGORITHM = "RS256"

Role = Literal["student", "admin"]

# Verified against when the account doesn't exist, so a failed login takes the same time
DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


@lru_cache
def _load_private_key(pem: str) -> RSAPrivateKey:
    # Parsed once instead of on every login; config.py has already checked it is an RSA key
    key = load_pem_private_key(pem.encode(), password=None)
    assert isinstance(key, RSAPrivateKey)
    return key


def _private_key(settings: Settings) -> RSAPrivateKey:
    if settings.jwt_private_key is None:
        raise RuntimeError("Set JWT_PRIVATE_KEY (the RSA key that signs access tokens)")
    return _load_private_key(settings.jwt_private_key.get_secret_value())


def public_key(settings: Settings) -> RSAPublicKey:
    return _private_key(settings).public_key()


def create_access_token(account_id: int, role: Role, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        # PyJWT requires "sub" to be a string
        "sub": str(account_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_access_token_ttl_seconds),
    }
    return jwt.encode(payload, _private_key(settings), algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    # Raises jwt.InvalidTokenError (bad signature, expired, malformed, missing claims)
    return jwt.decode(
        token,
        public_key(settings),
        # Pinning the algorithm stops a forged token from choosing "none", or HS256 with the public key as its secret
        algorithms=[ALGORITHM],
        options={"require": ["sub", "role", "exp"]},
    )