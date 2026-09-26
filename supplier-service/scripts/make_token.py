# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated development-only script that signs a test access token; AI-renamed its claim to "type" (Claude Code, 2026-09-27).
# Author review: <to be completed by author>

"""Print an access token for local testing, signed the same way the User Service signs them.

    uv run python scripts/make_token.py --type admin
    uv run python scripts/make_token.py --type student --sub 7 --minutes 30

Uses JWT_SECRET from the environment or supplier-service/.env (DATABASE_URL must be set there too). For development only:
once the User Service can sign users in, use the token it returns instead.
"""

import argparse
import time

import jwt

from supplier_service.config import get_settings

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--type", choices=["student", "admin"], default="student")
parser.add_argument("--sub", help="user id to put in the token (default: 1)")
parser.add_argument("--minutes", type=int, default=120, help="how long the token stays valid")
args = parser.parse_args()

now = int(time.time())
claims = {
    "sub": args.sub or "1",
    "type": args.type,
    "iat": now,
    "exp": now + args.minutes * 60,
}
settings = get_settings()
print(jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm))
