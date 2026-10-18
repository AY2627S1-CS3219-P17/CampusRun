# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated errands and outbox tables with the constraints that keep each errand's state, courier and
#        credit status consistent; the outbox table copied from user-service/tables.py.
# Author review: <to be completed by author>

"""Database schema (SQLAlchemy Core).

errands      one row per errand: who asked, who's delivering, its state and where its credits are
outbox       credit commands waiting to be published to RabbitMQ by order-worker

User and supplier ids belong to other services, so they are plain integers here: there are no foreign keys across
services because each owns its own database. delivery_location_id gets its foreign key when the delivery_locations
table moves into this service (docs/order-service-plan.md, Task 3).
"""

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

from order_service.states import IN_PROGRESS, CancelReason, CreditStatus, State

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

# Limits shared with input validation (and the create-request form)
TITLE_MAX_LENGTH = 100
REWARD_MIN = 1
REWARD_MAX = 100


def _sql_in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _timestamps() -> list[Column]:
    return [
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        # Only applies to updates issued through SQLAlchemy
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    ]


errands = Table(
    "errands",
    metadata,
    # Also the errandId in every credit command, so the Credit Service's reservation is keyed by it
    Column("id", Integer, Identity(), primary_key=True),
    Column("requester_id", Integer, nullable=False),
    # Set when a courier accepts
    Column("courier_id", Integer, nullable=True),
    Column("state", String(16), nullable=False),
    Column("credit_status", String(16), nullable=False),
    # The Credit Service's last refusal for this errand (e.g. INSUFFICIENT_CREDITS), to show the requester
    Column("credit_rejection", String(32), nullable=True),
    Column("title", String(TITLE_MAX_LENGTH), nullable=False),
    Column("reward", Integer, nullable=False),
    # Raised with every reward change and sent with AdjustReservation, so a late reply to an older change is ignored
    Column("reward_revision", Integer, nullable=False, server_default=text("0")),
    Column("supplier_id", Integer, nullable=False),
    Column("delivery_location_id", Integer, nullable=False),
    # The soft deadline the requester sets; the errand expires once the grace period after it has passed too
    Column("deliver_by", DateTime(timezone=True), nullable=False),
    Column("cancel_reason", String(32), nullable=True),
    *_timestamps(),
    Column("accepted_at", DateTime(timezone=True), nullable=True),
    Column("picked_up_at", DateTime(timezone=True), nullable=True),
    Column("delivered_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("cancelled_at", DateTime(timezone=True), nullable=True),
    Column("expired_at", DateTime(timezone=True), nullable=True),
    CheckConstraint(f"state IN ({_sql_in(State)})", name="state"),
    CheckConstraint(f"credit_status IN ({_sql_in(CreditStatus)})", name="credit_status"),
    CheckConstraint(f"reward BETWEEN {REWARD_MIN} AND {REWARD_MAX}", name="reward_range"),
    CheckConstraint("reward_revision >= 0", name="reward_revision_not_negative"),
    # Nobody can be the courier of their own errand, even if the code had a bug
    CheckConstraint("courier_id <> requester_id", name="courier_is_not_requester"),
    # OPEN and CANCELLED errands never had a courier; errands in progress or completed always have one.
    # EXPIRED can be either, since unfinished errands expire whether or not they were accepted.
    CheckConstraint(
        f"state NOT IN ('{State.OPEN}', '{State.CANCELLED}') OR courier_id IS NULL", name="no_courier_before_accept"
    ),
    CheckConstraint(
        f"state NOT IN ({_sql_in(sorted(IN_PROGRESS | {State.COMPLETED}))}) OR courier_id IS NOT NULL",
        name="courier_once_accepted",
    ),
    CheckConstraint(
        f"(state = '{State.CANCELLED}') = (cancel_reason IS NOT NULL)", name="cancel_reason_only_when_cancelled"
    ),
    CheckConstraint(f"cancel_reason IN ({_sql_in(CancelReason)})", name="cancel_reason"),
)

# Explore: OPEN errands with held credits, before their deadline
Index("ix_errands_state_credit_status_deliver_by", errands.c.state, errands.c.credit_status, errands.c.deliver_by)
# My Requests and My Tasks
Index("ix_errands_requester_id_state", errands.c.requester_id, errands.c.state)
Index("ix_errands_courier_id_state", errands.c.courier_id, errands.c.state)
# The reconciler: credits that have been PENDING for too long
Index("ix_errands_credit_status_updated_at", errands.c.credit_status, errands.c.updated_at)
# The sweeper: unfinished errands past their deadline
Index("ix_errands_deliver_by", errands.c.deliver_by)

# Transactional outbox, as in user-service: a credit command is inserted here in the same transaction as the
# change that causes it, and order-worker publishes it afterwards. So an errand is never committed without its
# command, and a command is never sent for a change that rolled back.
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
