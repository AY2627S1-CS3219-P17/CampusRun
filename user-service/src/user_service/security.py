# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated shared Argon2 password hasher (pwdlib).
# Author review: reviewed by Nathan

from pwdlib import PasswordHash

# Argon2id with pwdlib's recommended parameters; shared so every account type hashes the same way
password_hash = PasswordHash.recommended()
