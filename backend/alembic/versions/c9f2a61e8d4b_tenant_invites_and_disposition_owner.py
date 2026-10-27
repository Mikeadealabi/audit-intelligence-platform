"""tenant_invite table + finding.disposition_recorded_by

Revision ID: c9f2a61e8d4b
Revises: b7e4d82f1c3a
Create Date: 2026-10-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c9f2a61e8d4b'
down_revision: Union[str, None] = 'b7e4d82f1c3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('finding', sa.Column('disposition_recorded_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_finding_disposition_recorded_by_app_user', 'finding', 'app_user', ['disposition_recorded_by'], ['id']
    )

    op.create_table(
        'tenant_invite',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('invited_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('accepted_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['invited_by'], ['app_user.id']),
        sa.ForeignKeyConstraint(['accepted_by'], ['app_user.id']),
        sa.ForeignKeyConstraint(['revoked_by'], ['app_user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_tenant_invite_token_hash'),
    )
    # No separate index on token_hash — the UniqueConstraint above already gives
    # it a unique index for the exact-match lookup in invites.py.
    op.create_index(op.f('ix_tenant_invite_tenant_id'), 'tenant_invite', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tenant_invite_tenant_id'), table_name='tenant_invite')
    op.drop_table('tenant_invite')

    op.drop_constraint('fk_finding_disposition_recorded_by_app_user', 'finding', type_='foreignkey')
    op.drop_column('finding', 'disposition_recorded_by')
