# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated metadata with the naming convention used by the other services' tables.py.
# Author review: <to be completed by author>

"""Database schema (SQLAlchemy Core).

The tables (delivery_locations, errands, outbox) are added in later steps of docs/order-service-plan.md. The naming
convention is set before the first migration so every constraint gets a predictable name.

User and supplier ids belong to other services, so they are plain integers here: there are no foreign keys across
services because each owns its own database.
"""

from sqlalchemy import MetaData

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
