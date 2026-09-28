"""add role to users, drop admins

Revision ID: cb86242157bd
Revises: 717eccffe95a
Create Date: 2026-09-28 12:00:00.000000

"""
# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-28
# Scope: AI-written migration replacing the separate admins table with a role column on users.
# Author review: <to be completed by author>
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb86242157bd'
down_revision: Union[str, Sequence[str], None] = '717eccffe95a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing users are students; the default fills the column for them
    op.add_column('users', sa.Column('role', sa.String(length=16), server_default='student', nullable=False))
    op.create_check_constraint(op.f('ck_users_role'), 'users', "role IN ('student', 'admin')")
    # Old admin rows have no email, so they can't become users; re-create them with create-initial-admin
    op.drop_index('uq_admins_username_lower', table_name='admins')
    op.drop_table('admins')


def downgrade() -> None:
    """Downgrade schema."""
    # Admins stay in users as ordinary accounts; they aren't moved back into the admins table
    op.create_table('admins',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('username', sa.String(length=32), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admins'))
    )
    op.create_index('uq_admins_username_lower', 'admins', [sa.literal_column('lower(username)')], unique=True)
    op.drop_constraint(op.f('ck_users_role'), 'users', type_='check')
    op.drop_column('users', 'role')
