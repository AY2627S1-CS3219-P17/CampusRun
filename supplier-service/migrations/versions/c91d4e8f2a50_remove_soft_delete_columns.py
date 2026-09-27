# AI Assistance Disclosure:
# Tool: Codex (model: GPT-5), date: 2026-09-27
# Scope: AI-generated forward migration removing obsolete soft-delete columns and partial unique indexes.
# Author review: <to be completed by author>

"""remove soft-delete columns

Revision ID: c91d4e8f2a50
Revises: b037ea030fac
Create Date: 2026-09-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91d4e8f2a50"
down_revision: Union[str, Sequence[str], None] = "b037ea030fac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove legacy soft-delete state after rejecting duplicate historical names."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM suppliers
                GROUP BY lower(name)
                HAVING count(*) > 1
            ) OR EXISTS (
                SELECT 1 FROM delivery_locations
                GROUP BY lower(name)
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot remove soft-delete columns while duplicate names exist.';
            END IF;
        END $$;
        """
    )

    op.drop_index(
        "uq_suppliers_name_lower",
        table_name="suppliers",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_column("suppliers", "deleted_at")
    op.create_index(
        "uq_suppliers_name_lower",
        "suppliers",
        [sa.literal_column("lower(name)")],
        unique=True,
    )

    op.drop_index(
        "uq_delivery_locations_name_lower",
        table_name="delivery_locations",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_column("delivery_locations", "deleted_at")
    op.create_index(
        "uq_delivery_locations_name_lower",
        "delivery_locations",
        [sa.literal_column("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    """Restore soft-delete storage and its partial case-insensitive indexes."""
    op.drop_index("uq_delivery_locations_name_lower", table_name="delivery_locations")
    op.add_column(
        "delivery_locations",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_delivery_locations_name_lower",
        "delivery_locations",
        [sa.literal_column("lower(name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.drop_index("uq_suppliers_name_lower", table_name="suppliers")
    op.add_column(
        "suppliers", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_suppliers_name_lower",
        "suppliers",
        [sa.literal_column("lower(name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )