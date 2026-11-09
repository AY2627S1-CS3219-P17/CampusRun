# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated development-only script that signs a test access token; AI-renamed its claim to "type" (Claude Code, 2026-09-27), then to "role" (2026-09-28).
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-changed the script to sign with the User Service's RS256 private key instead of JWT_SECRET.
# Author review: <to be completed by author>

"""Print an access token for local testing, signed the same way the User Service signs them.

    uv run python scripts/make_token.py --role admin
    uv run python scripts/make_token.py --role student --sub 7 --minutes 30

Needs JWT_PRIVATE_KEY, the User Service's signing key from the root .env, in the environment or supplier-service/.env.
The supplier service itself never uses that key. For development only: when the User Service is running, you can
sign in there and use the token it returns instead.
"""

import argparse
import time

import jwt
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SigningSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_private_key: SecretStr


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--role", choices=["student", "admin"], default="student")
parser.add_argument("--sub", help="user id to put in the token (default: 1)")
parser.add_argument("--minutes", type=int, default=120, help="how long the token stays valid")
args = parser.parse_args()

now = int(time.time())
claims = {
    "sub": args.sub or "1",
    "role": args.role,
    "iat": now,
    "exp": now + args.minutes * 60,
}
# .env files often hold the PEM on one line with literal \n
private_key = SigningSettings().jwt_private_key.get_secret_value().strip().replace("\\n", "\n")  # pyright: ignore[reportCallIssue]
print(jwt.encode(claims, private_key, algorithm="RS256"))
