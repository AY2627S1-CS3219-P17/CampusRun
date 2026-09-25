# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated SQLAlchemy Core MetaData naming convention and users/admins table definitions.
# Author review: Reviewed and added email_verified_at

from sqlalchemy import (
    Column,
    DateTime,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
)

# Deterministic constraint names, so Alembic migrations can refer to them
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def _timestamps() -> list[Column]:
    return [
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            # Only applies to updates issued through SQLAlchemy
            onupdate=func.now(),
        ),
    ]


users = Table(
    "users",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("email", String(254), nullable=False),
    # Null until the user confirms they own the email address
    Column("email_verified_at", DateTime(timezone=True), nullable=True),
    Column("username", String(32), nullable=False),
    Column("password_hash", Text, nullable=False),
    # URL or object-storage key; the image itself lives outside the database
    Column("profile_picture_url", Text, nullable=True),
    *_timestamps(),
)

admins = Table(
    "admins",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("username", String(32), nullable=False),
    Column("password_hash", Text, nullable=False),
    *_timestamps(),
)

# Case-insensitive uniqueness: "Alice@u.nus.edu" and "alice@u.nus.edu" are the same account
Index("uq_users_email_lower", func.lower(users.c.email), unique=True)
Index("uq_users_username_lower", func.lower(users.c.username), unique=True)
Index("uq_admins_username_lower", func.lower(admins.c.username), unique=True)
