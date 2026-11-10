#!/bin/sh
# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-generated script that makes the RSA key pair for RS256 access tokens.
# Author review: I tested the behaviour: it writes a working key pair for RS256 tokens.
#
# Prints JWT_PRIVATE_KEY and JWT_PUBLIC_KEY lines for the root .env, each PEM on one line with \n escapes:
#
#   sh scripts/generate-jwt-keys.sh >> .env
#
# Remove any older JWT_PRIVATE_KEY / JWT_PUBLIC_KEY lines from .env first. A new pair signs out everyone, since
# tokens signed with the old key stop verifying.
set -eu

private_key=$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null)
public_key=$(printf '%s\n' "$private_key" | openssl pkey -pubout)

# Joins the PEM's lines with a literal \n, which Compose and python-dotenv turn back into newlines
one_line() {
  printf '%s\n' "$1" | awk 'BEGIN { ORS = "" } { print $0 "\\n" }'
}

# printf, not echo: some shells' echo would turn the \n back into line breaks
printf 'JWT_PRIVATE_KEY="%s"\n' "$(one_line "$private_key")"
printf 'JWT_PUBLIC_KEY="%s"\n' "$(one_line "$public_key")"
