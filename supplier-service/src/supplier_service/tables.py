# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated suppliers and delivery_locations tables, indexes and constraints,
#        following the conventions in user-service/tables.py.
# Author review: <to be completed by author>

"""Database schema (SQLAlchemy Core).

Two independent tables. Other services refer to rows here only by id; there
are no foreign keys across services because each owns its own database.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Double,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Time,
    func,
    literal_column,
    true,
)

# The values the web client uses (frontend/src/types/supplier.ts)
SUPPLIER_TYPES = ("Food", "Drinks", "Shopping", "Printing")

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


def _audit_and_soft_delete() -> list[Column]:
    return [
        # User id (token "sub") of the admin who created or last changed the row
        Column("created_by", String(64), nullable=True),
        Column("updated_by", String(64), nullable=True),
        # Soft delete: errands in the Order Service may still refer to this id
        Column("deleted_at", DateTime(timezone=True), nullable=True),
    ]


suppliers = Table(
    "suppliers",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("type", String(20), nullable=False),
    Column("building", String(100), nullable=False),
    Column("floor", String(10), nullable=True),
    Column("location_description", String(300), nullable=False),
    Column("latitude", Double, nullable=False),
    Column("longitude", Double, nullable=False),
    # Local campus time. end_time earlier than start_time means it closes after midnight.
    Column("start_time", Time, nullable=False),
    Column("end_time", Time, nullable=False),
    Column("image_url", String(500), nullable=True),
    Column("active", Boolean, nullable=False, server_default=true()),
    *_timestamps(),
    *_audit_and_soft_delete(),
    CheckConstraint(
        f"type IN ({', '.join(repr(t) for t in SUPPLIER_TYPES)})",
        name="type",
    ),
    CheckConstraint(
        "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
        name="coordinates",
    ),
)

delivery_locations = Table(
    "delivery_locations",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("description", String(300), nullable=False),
    Column("latitude", Double, nullable=False),
    Column("longitude", Double, nullable=False),
    Column("active", Boolean, nullable=False, server_default=true()),
    *_timestamps(),
    *_audit_and_soft_delete(),
    CheckConstraint(
        "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
        name="coordinates",
    ),
)

# Text that keyword search runs over. Built with || (not concat_ws) so Postgres
# accepts it in an index; queries must use this exact expression to use the index.
_SPACE = literal_column("' '")
supplier_search_text = (
    suppliers.c.name
    + _SPACE
    + suppliers.c.building
    + _SPACE
    + suppliers.c.location_description
)

# F4.1.4: names are unique regardless of case, among rows that are not deleted
Index(
    "uq_suppliers_name_lower",
    func.lower(suppliers.c.name),
    unique=True,
    postgresql_where=suppliers.c.deleted_at.is_(None),
)
Index("ix_suppliers_type", suppliers.c.type)
Index("ix_suppliers_building_lower", func.lower(suppliers.c.building))
# N3.1.1: trigram index so ILIKE '%keyword%' doesn't need a full table scan.
# Needs the pg_trgm extension, which the first migration creates.
Index(
    "ix_suppliers_search_trgm",
    supplier_search_text.label("search_text"),
    postgresql_using="gin",
    postgresql_ops={"search_text": "gin_trgm_ops"},
)
Index(
    "uq_delivery_locations_name_lower",
    func.lower(delivery_locations.c.name),
    unique=True,
    postgresql_where=delivery_locations.c.deleted_at.is_(None),
)
