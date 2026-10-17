"""reconciliation subsystem: external_record_batch/external_record/reconciliation_run/reconciliation_match + import_run.source_label

Revision ID: e7f3a9c21b44
Revises: d4a1f6c0e92b
Create Date: 2026-10-17 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e7f3a9c21b44'
down_revision: Union[str, None] = 'd4a1f6c0e92b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only used by the external-record (reconciliation) import flow; null for the
    # existing transaction-record import flow. Nullable, no default needed.
    op.add_column('import_run', sa.Column('source_label', sa.String(length=200), nullable=True))

    op.create_table(
        'external_record_batch',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('engagement_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('import_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_label', sa.String(length=200), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('source_file_sha256', sa.String(length=64), nullable=False),
        sa.Column('mapping_snapshot', sa.JSON(), nullable=False),
        sa.Column('committed_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('committed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagement.id']),
        sa.ForeignKeyConstraint(['import_run_id'], ['import_run.id']),
        sa.ForeignKeyConstraint(['committed_by'], ['app_user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('import_run_id', name='uq_external_record_batch_import_run'),
    )
    op.create_index(op.f('ix_external_record_batch_tenant_id'), 'external_record_batch', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_external_record_batch_engagement_id'), 'external_record_batch', ['engagement_id'], unique=False)

    op.create_table(
        'external_record',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('engagement_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_record_batch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_row_number', sa.Integer(), nullable=False),
        sa.Column('counterparty_name', sa.String(length=300), nullable=True),
        sa.Column('reference', sa.String(length=200), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=True),
        sa.Column('amount', sa.Numeric(18, 2), nullable=True),
        sa.Column('transaction_date', sa.Date(), nullable=True),
        sa.Column('raw_row', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagement.id']),
        sa.ForeignKeyConstraint(['external_record_batch_id'], ['external_record_batch.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_external_record_tenant_id'), 'external_record', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_external_record_engagement_id'), 'external_record', ['engagement_id'], unique=False)
    op.create_index(
        op.f('ix_external_record_external_record_batch_id'), 'external_record', ['external_record_batch_id'], unique=False
    )

    op.create_table(
        'reconciliation_run',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('engagement_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dataset_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_record_batch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('method', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('run_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('matched_count', sa.Integer(), nullable=False),
        sa.Column('unmatched_transaction_count', sa.Integer(), nullable=False),
        sa.Column('unmatched_external_count', sa.Integer(), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagement.id']),
        sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_version.id']),
        sa.ForeignKeyConstraint(['external_record_batch_id'], ['external_record_batch.id']),
        sa.ForeignKeyConstraint(['run_by'], ['app_user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reconciliation_run_tenant_id'), 'reconciliation_run', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_reconciliation_run_engagement_id'), 'reconciliation_run', ['engagement_id'], unique=False)

    op.create_table(
        'reconciliation_match',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('engagement_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reconciliation_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transaction_record_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('external_record_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('match_status', sa.String(length=30), nullable=False),
        sa.Column('match_basis', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagement.id']),
        sa.ForeignKeyConstraint(['reconciliation_run_id'], ['reconciliation_run.id']),
        sa.ForeignKeyConstraint(['transaction_record_id'], ['transaction_record.id']),
        sa.ForeignKeyConstraint(['external_record_id'], ['external_record.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reconciliation_match_tenant_id'), 'reconciliation_match', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_reconciliation_match_engagement_id'), 'reconciliation_match', ['engagement_id'], unique=False)
    op.create_index(
        op.f('ix_reconciliation_match_reconciliation_run_id'), 'reconciliation_match', ['reconciliation_run_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_reconciliation_match_reconciliation_run_id'), table_name='reconciliation_match')
    op.drop_index(op.f('ix_reconciliation_match_engagement_id'), table_name='reconciliation_match')
    op.drop_index(op.f('ix_reconciliation_match_tenant_id'), table_name='reconciliation_match')
    op.drop_table('reconciliation_match')

    op.drop_index(op.f('ix_reconciliation_run_engagement_id'), table_name='reconciliation_run')
    op.drop_index(op.f('ix_reconciliation_run_tenant_id'), table_name='reconciliation_run')
    op.drop_table('reconciliation_run')

    op.drop_index(op.f('ix_external_record_external_record_batch_id'), table_name='external_record')
    op.drop_index(op.f('ix_external_record_engagement_id'), table_name='external_record')
    op.drop_index(op.f('ix_external_record_tenant_id'), table_name='external_record')
    op.drop_table('external_record')

    op.drop_index(op.f('ix_external_record_batch_engagement_id'), table_name='external_record_batch')
    op.drop_index(op.f('ix_external_record_batch_tenant_id'), table_name='external_record_batch')
    op.drop_table('external_record_batch')

    op.drop_column('import_run', 'source_label')
