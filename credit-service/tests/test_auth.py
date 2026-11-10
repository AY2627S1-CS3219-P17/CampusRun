# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-generated tests for RS256 token checks: forged keys, "none" and HS256 keyed with the public key are refused.
# Author review: I ran the tests; forged, "none" and HS256 tokens are all refused.

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from credit_service.auth import decode_token
from .conftest import TEST_PUBLIC_PEM, make_token

OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLAIMS = {"sub": "7", "role": "admin", "exp": int(time.time()) + 300}


def hs256_signed_with(secret: str, claims: dict) -> str:
    """The algorithm-confusion attack: HS256 keyed with the RSA public key, which every service has. PyJWT refuses to
    make such a token, so it's built by hand."""

    def b64(data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    signing_input = b64(b'{"alg":"HS256","typ":"JWT"}') + b"." + b64(json.dumps(claims).encode())
    signature = b64(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + signature).decode()


def test_a_token_signed_by_the_user_service_key_is_accepted():
    assert decode_token(make_token("student", "7")).id == 7


@pytest.mark.parametrize(
    "token",
    [
        make_token("student", "7", key=OTHER_KEY),
        jwt.encode(CLAIMS, None, algorithm="none"),
        hs256_signed_with(TEST_PUBLIC_PEM, CLAIMS),
    ],
    ids=["other-key", "alg-none", "hs256-with-public-key"],
)
def test_forged_tokens_are_refused(token):
    with pytest.raises(HTTPException) as refused:
        decode_token(token)
    assert refused.value.status_code == 401
