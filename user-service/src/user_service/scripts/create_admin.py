# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated create-initial-admin script that seeds the first admin from INITIAL_ADMIN_* settings;
#        AI-changed it to create a user with the admin role, validated like a registration (2026-09-28).
# Author review: reviewed by Nathan

import asyncio
import sys

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from user_service.config import Settings, get_settings
from user_service.db import create_engine
from user_service.schemas import RegisterRequest
from user_service.security import password_hash
from user_service.tables import users


def _validated(settings: Settings) -> RegisterRequest:
    email = (settings.initial_admin_email or "").strip()
    username = (settings.initial_admin_username or "").strip()
    password = settings.initial_admin_password.get_secret_value() if settings.initial_admin_password else ""
    if not email or not username or not password:
        raise ValueError("INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD must all be set")
    # Same rules as registration, including the @u.nus.edu email
    try:
        return RegisterRequest(email=email, username=username, password=password)
    except ValidationError as error:
        problems = "; ".join(
            f"INITIAL_ADMIN_{str(e['loc'][0]).upper()} {e['msg'].removeprefix('Value error, ')}" for e in error.errors()
        )
        raise ValueError(problems) from None


async def create_initial_admin(settings: Settings) -> str:
    admin = _validated(settings)

    engine = create_engine(settings)
    try:
        async with engine.begin() as conn:
            # Only seeds when there's no admin, so these env vars can't be used to add admins later
            existing = await conn.scalar(select(func.count()).select_from(users).where(users.c.role == "admin"))
            if existing:
                return "Skipped: an admin already exists"

            # Relies on the case-insensitive unique indexes; also guards against a concurrent run inserting first
            created = await conn.scalar(
                insert(users)
                .values(
                    email=admin.email,
                    username=admin.username,
                    password_hash=password_hash.hash(admin.password),
                    role="admin",
                )
                .on_conflict_do_nothing()
                .returning(users.c.id)
            )
            if created is not None:
                return f"Created initial admin '{admin.username}'"

            # Nothing inserted: either a concurrent run won, or a student already has this email or username
            taken_by_admin = await conn.scalar(
                select(func.count())
                .select_from(users)
                .where(
                    users.c.role == "admin",
                    func.lower(users.c.username) == admin.username.lower(),
                )
            )
            if taken_by_admin:
                return "Skipped: an admin already exists"
            raise ValueError("INITIAL_ADMIN_EMAIL or INITIAL_ADMIN_USERNAME is already used by another account")
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
