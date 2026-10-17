"""optional tax fields on transaction_record + control_configuration table

Revision ID: d4a1f6c0e92b
Revises: f2a72435b50d
Create Date: 2026-10-17 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4a1f6c0e92b'
down_revision: Union[str, None] = 'f2a72435b50d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, no server default needed — these are optional fields that stay
    # None unless a source file actually maps a column to them (see
    # app/services/csv_parser.py OPTIONAL_CANONICAL_FIELDS). Safe to add to a
    # table that already has rows.
    op.add_column('transaction_record', sa.Column('tax_category', sa.String(length=100), nullable=True))
    op.add_column('transaction_record', sa.Column('recorded_vat_amount', sa.Numeric(18, 2), nullable=True))
    op.add_column('transaction_record', sa.Column('recorded_wht_amount', sa.Numeric(18, 2), nullable=True))

    op.create_table(
        'control_configuration',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('engagement_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('control_code', sa.String(length=100), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('parameters', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagement.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['app_user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('engagement_id', 'control_code', name='uq_control_configuration_engagement_control'),
    )
    op.create_index(
        op.f('ix_control_configuration_tenant_id'), 'control_configuration', ['tenant_id'], unique=False
    )
    op.create_index(
        op.f('ix_control_configuration_engagement_id'), 'control_configuration', ['engagement_id'], unique=False
    )
    op.alter_column('control_configuration', 'enabled', server_default=None)
    op.alter_column('control_configuration', 'parameters', server_default=None)


def downgrade() -> None:
    op.drop_index(op.f('ix_control_configuration_engagement_id'), table_name='control_configuration')
    op.drop_index(op.f('ix_control_configuration_tenant_id'), table_name='control_configuration')
    op.drop_table('control_configuration')
    op.drop_column('transaction_record', 'recorded_wht_amount')
    op.drop_column('transaction_record', 'recorded_vat_amount')
    op.drop_column('transaction_record', 'tax_category')
