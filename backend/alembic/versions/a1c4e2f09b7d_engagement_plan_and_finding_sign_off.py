"""engagement_plan table + finding sign-off columns

Revision ID: a1c4e2f09b7d
Revises: e7f3a9c21b44
Create Date: 2026-10-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1c4e2f09b7d'
down_revision: Union[str, None] = 'e7f3a9c21b44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Effectively non-null-with-a-default (the app model defaults to
    # "not_required") — add with a server default so existing rows backfill
    # cleanly, then drop the server default so the Python-side default governs
    # all future inserts (same two-step pattern as control_configuration.enabled).
    op.add_column(
        'finding',
        sa.Column('sign_off_status', sa.String(length=20), nullable=False, server_default='not_required'),
    )
    op.alter_column('finding', 'sign_off_status', server_default=None)
    op.add_column('finding', sa.Column('signed_off_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('finding', sa.Column('signed_off_at', sa.DateTime(), nullable=True))
    op.create_foreign_key(
        'fk_finding_signed_off_by_app_user', 'finding', 'app_user', ['signed_off_by'], ['id']
    )

    op.create_table(
        'engagement_plan',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('engagement_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('materiality_amount', sa.Numeric(18, 2), nullable=True),
        sa.Column('materiality_currency', sa.String(length=10), nullable=True),
        sa.Column('scope_notes', sa.String(length=4000), nullable=True),
        sa.Column('risk_assessment', sa.String(length=4000), nullable=True),
        sa.Column('risk_rating', sa.String(length=10), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagement.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['app_user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('engagement_id', name='uq_engagement_plan_engagement'),
    )
    op.create_index(op.f('ix_engagement_plan_tenant_id'), 'engagement_plan', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_engagement_plan_engagement_id'), 'engagement_plan', ['engagement_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_engagement_plan_engagement_id'), table_name='engagement_plan')
    op.drop_index(op.f('ix_engagement_plan_tenant_id'), table_name='engagement_plan')
    op.drop_table('engagement_plan')

    op.drop_constraint('fk_finding_signed_off_by_app_user', 'finding', type_='foreignkey')
    op.drop_column('finding', 'signed_off_at')
    op.drop_column('finding', 'signed_off_by')
    op.drop_column('finding', 'sign_off_status')
