# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated create-initial-admin script that seeds the first admin from INITIAL_ADMIN_* settings.
# Author review: <to be completed by author>

import asyncio
import sys

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from user_service.config import Settings, get_settings
from user_service.db import create_engine
from user_service.security import password_hash
from user_service.tables import USERNAME_MAX_LENGTH, admins


async def create_initial_admin(settings: Settings) -> str:
    username = (settings.initial_admin_username or "").strip()
    password = (
        settings.initial_admin_password.get_secret_value()
        if settings.initial_admin_password
        else ""
    )
    if not username or not password:
        raise ValueError("INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD must both be set")
    if len(username) > USERNAME_MAX_LENGTH:
        raise ValueError(f"INITIAL_ADMIN_USERNAME must be at most {USERNAME_MAX_LENGTH} characters")

    engine = create_engine(settings)
    try:
        async with engine.begin() as conn:
            # Only seeds an empty table, so these env vars can't be used to add admins later
            existing = await conn.scalar(select(func.count()).select_from(admins))
            if existing:
                return "Skipped: an admin already exists"

            # Guards against a concurrent run inserting the same username first
            created = await conn.scalar(
                insert(admins)
                .values(username=username, password_hash=password_hash.hash(password))
                .on_conflict_do_nothing()
                .returning(admins.c.id)
            )
            if created is None:
                return "Skipped: an admin already exists"
            return f"Created initial admin '{username}'"
    finally:
        await engine.dispose()


def main() -> None:
    try:
        message = asyncio.run(create_initial_admin(get_settings()))
    except ValueError as error:
        sys.exit(f"Error: {error}")
    print(message)


if __name__ == "__main__":
    main()
