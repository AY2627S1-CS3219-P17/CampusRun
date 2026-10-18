"""add outbox, and queue a wallet for every existing user

Revision ID: 7cb330b8ad8a
Revises: cb86242157bd
Create Date: 2026-10-17 12:00:00.000000

"""
# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-written migration adding the outbox table and an OpenWallet message for each user registered before it.
# Author review: <to be completed by author>
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7cb330b8ad8a'
down_revision: Union[str, Sequence[str], None] = 'cb86242157bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('outbox',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('message_id', postgresql.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('exchange', sa.String(length=64), nullable=False),
    sa.Column('routing_key', sa.String(length=64), nullable=False),
    sa.Column('message_type', sa.String(length=64), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox'))
    )
    op.create_index('uq_outbox_message_id', 'outbox', ['message_id'], unique=True)
    op.create_index('ix_outbox_unpublished', 'outbox', ['id'], unique=False, postgresql_where=sa.text('published_at IS NULL'))
    # Users who registered before the credit service existed have no wallet yet. The credit service ignores
    # OpenWallet for users who already have one, so this is safe even if some do.
    op.execute(
        "INSERT INTO outbox (exchange, routing_key, message_type, payload) "
        "SELECT 'credit.commands', 'wallet.open', 'OpenWallet', jsonb_build_object('userId', id) FROM users ORDER BY id"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_outbox_unpublished', table_name='outbox', postgresql_where=sa.text('published_at IS NULL'))
    op.drop_index('uq_outbox_message_id', table_name='outbox')
    op.drop_table('outbox')
