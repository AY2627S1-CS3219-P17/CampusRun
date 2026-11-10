"""add refresh_sessions

Revision ID: 3f9a2c71d4e8
Revises: 7cb330b8ad8a
Create Date: 2026-11-09 12:00:00.000000

"""
# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
# Scope: AI-written migration adding the refresh_sessions table for refresh-token rotation.
# Author review: I tested the behaviour: the migration upgrades and downgrades cleanly.
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3f9a2c71d4e8'
down_revision: Union[str, Sequence[str], None] = '7cb330b8ad8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('refresh_sessions',
    sa.Column('id', postgresql.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.LargeBinary(), nullable=False),
    sa.Column('previous_hash', sa.LargeBinary(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_sessions'))
    )
    op.create_index('uq_refresh_sessions_token_hash', 'refresh_sessions', ['token_hash'], unique=True)
    op.create_index('ix_refresh_sessions_previous_hash', 'refresh_sessions', ['previous_hash'], unique=False)
    op.create_index('ix_refresh_sessions_user_id', 'refresh_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_refresh_sessions_user_id', table_name='refresh_sessions')
    op.drop_index('ix_refresh_sessions_previous_hash', table_name='refresh_sessions')
    op.drop_index('uq_refresh_sessions_token_hash', table_name='refresh_sessions')
    op.drop_table('refresh_sessions')
