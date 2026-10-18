# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for wallets, reservations and ledger_entries tables with the constraints that keep the
#        credit economy consistent, following the conventions in supplier-service/tables.py.
# Author review: <to be completed by author>

"""Database schema (SQLAlchemy Core).

wallets          one row per user: the current available and reserved balances (total is computed by Postgres)
reservations     one row per errand: the credits held for it and what happened to them
ledger_entries   append-only: one row per change to a wallet, so every balance can be re-derived (N5.2.1)

User and errand ids belong to the User and Order Services, so they are plain integers here: there are no
foreign keys across services because each owns its own database.
"""

from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    func,
    text,
)

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class ReservationStatus(StrEnum):
    HELD = "HELD"  # credits moved from available to reserved; the errand hasn't ended
    TRANSFERRED = "TRANSFERRED"  # paid to the courier
    RELEASED = "RELEASED"  # returned to the requester's available balance
    REJECTED = "REJECTED"  # never held: not enough credits, no wallet, or cancelled before the hold arrived


class EntryKind(StrEnum):
    INITIAL_ALLOCATION = "INITIAL_ALLOCATION"  # the only way credits enter the economy (F14.1)
    RESERVE = "RESERVE"  # available -> reserved
    RELEASE = "RELEASE"  # reserved -> available
    TRANSFER_OUT = "TRANSFER_OUT"  # requester's reserved -> (leaves the requester)
    TRANSFER_IN = "TRANSFER_IN"  # (arrives at the courier) -> courier's available


def _sql_in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _timestamps() -> list[Column]:
    return [
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        # Only applies to updates issued through SQLAlchemy
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    ]


wallets = Table(
    "wallets",
    metadata,
    # The User Service's user id. A primary key, so a user can never get a second wallet (or a second allocation).
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("available", Integer, nullable=False),
    Column("reserved", Integer, nullable=False, server_default=text("0")),
    # Computed by Postgres on every write, so it can never disagree with available + reserved
    Column("total", Integer, Computed("available + reserved", persisted=True), nullable=False),
    *_timestamps(),
    # The last line of defence against overspending: no code path can commit a negative balance (F12.1.2)
    CheckConstraint("available >= 0", name="available_not_negative"),
    CheckConstraint("reserved >= 0", name="reserved_not_negative"),
)

reservations = Table(
    "reservations",
    metadata,
    # The Order Service's errand id. One reservation per errand: a repeated reserve message finds this row
    # instead of holding the credits twice.
    Column("errand_id", Integer, primary_key=True, autoincrement=False),
    Column("requester_id", Integer, nullable=False),
    # Set when the credits are transferred
    Column("courier_id", Integer, nullable=True),
    # Credits held for the errand (0 only for a REJECTED placeholder written by an early release)
    Column("amount", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    # Why it's REJECTED or RELEASED, e.g. INSUFFICIENT_CREDITS or EXPIRED
    Column("reason", String(32), nullable=True),
    # Raised by each AdjustReservation, so an older reward change arriving late is ignored (N7.1.1)
    Column("revision", Integer, nullable=False, server_default=text("0")),
    *_timestamps(),
    CheckConstraint(f"status IN ({_sql_in(ReservationStatus)})", name="status"),
    CheckConstraint("amount > 0 OR (amount = 0 AND status = 'REJECTED')", name="amount_positive"),
    CheckConstraint("(status = 'TRANSFERRED') = (courier_id IS NOT NULL)", name="courier_only_when_transferred"),
    CheckConstraint("courier_id <> requester_id", name="courier_is_not_requester"),
    CheckConstraint("revision >= 0", name="revision_not_negative"),
)

ledger_entries = Table(
    "ledger_entries",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("user_id", Integer, ForeignKey("wallets.user_id"), nullable=False),
    # Null only for the initial allocation
    Column("errand_id", Integer, nullable=True),
    Column("kind", String(24), nullable=False),
    Column("available_delta", Integer, nullable=False),
    Column("reserved_delta", Integer, nullable=False),
    # The balances right after this change, so a history reads like a bank statement
    Column("available_after", Integer, nullable=False),
    Column("reserved_after", Integer, nullable=False),
    # The RabbitMQ message that caused the change, to trace an entry back to its sender
    Column("message_id", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(f"kind IN ({_sql_in(EntryKind)})", name="kind"),
    # Each kind can only move credits the way its name says. RESERVE and RELEASE move credits between a
    # user's own balances, and the initial allocation is the only kind that adds credits overall.
    CheckConstraint(
        "(kind = 'INITIAL_ALLOCATION' AND available_delta > 0 AND reserved_delta = 0 AND errand_id IS NULL)"
        " OR (kind = 'RESERVE' AND available_delta < 0 AND reserved_delta = -available_delta)"
        " OR (kind = 'RELEASE' AND available_delta > 0 AND reserved_delta = -available_delta)"
        " OR (kind = 'TRANSFER_OUT' AND available_delta = 0 AND reserved_delta < 0)"
        " OR (kind = 'TRANSFER_IN' AND available_delta > 0 AND reserved_delta = 0)",
        name="kind_moves",
    ),
    CheckConstraint("available_after >= 0 AND reserved_after >= 0", name="after_not_negative"),
)

# A user's history, newest first (F14.2), and an errand's credit movements (F11.3.1)
Index("ix_ledger_entries_user_id_id", ledger_entries.c.user_id, ledger_entries.c.id)
Index("ix_ledger_entries_errand_id", ledger_entries.c.errand_id)
# At most one initial allocation per user, enforced by Postgres even if the code had a bug (F12.1.1)
Index(
    "uq_ledger_entries_initial_allocation",
    ledger_entries.c.user_id,
    unique=True,
    postgresql_where=ledger_entries.c.kind == EntryKind.INITIAL_ALLOCATION.value,
)
# The audit's stale-hold check and a requester's held total
Index("ix_reservations_requester_id_status", reservations.c.requester_id, reservations.c.status)
