# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated SQLAlchemy Core MetaData naming convention and users/admins table definitions;
#        AI-added USERNAME_MAX_LENGTH constant; AI-replaced the admins table with a role column on users (Claude Code, 2026-09-28);
#        AI-added the outbox table for messages to RabbitMQ (Claude, claude.ai, 2026-10-17).
# Author review: Reviewed and added email_verified_at

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Shared by the users table and input validation
USERNAME_MAX_LENGTH = 32

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
    Column("username", String(USERNAME_MAX_LENGTH), nullable=False),
    Column("password_hash", Text, nullable=False),
    # URL or object-storage key; the image itself lives outside the database
    Column("profile_picture_url", Text, nullable=True),
    # "student" or "admin"; only set to "admin" by the create-initial-admin script, never through the API
    Column("role", String(16), nullable=False, server_default="student"),
    *_timestamps(),
    CheckConstraint("role IN ('student', 'admin')", name="role"),
)

# Case-insensitive uniqueness: "Alice@u.nus.edu" and "alice@u.nus.edu" are the same account
Index("uq_users_email_lower", func.lower(users.c.email), unique=True)
Index("uq_users_username_lower", func.lower(users.c.username), unique=True)


# Transactional outbox: a message to another service is inserted here in the same transaction as the change that
# causes it, and the relay in outbox.py publishes it to RabbitMQ afterwards. So a registration is never committed
# without its OpenWallet message, and a message is never sent for a registration that rolled back.
outbox = Table(
    "outbox",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    # Sent as the AMQP message_id; the same on every retry, so the receiver can tell a repeat
    Column("message_id", UUID(as_uuid=False), nullable=False, server_default=text("gen_random_uuid()")),
    Column("exchange", String(64), nullable=False),
    Column("routing_key", String(64), nullable=False),
    Column("message_type", String(64), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Null until RabbitMQ has confirmed it has the message
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("last_error", Text, nullable=True),
)

Index("uq_outbox_message_id", outbox.c.message_id, unique=True)
# The relay only ever looks for unpublished rows, which stay few
Index("ix_outbox_unpublished", outbox.c.id, postgresql_where=outbox.c.published_at.is_(None))
