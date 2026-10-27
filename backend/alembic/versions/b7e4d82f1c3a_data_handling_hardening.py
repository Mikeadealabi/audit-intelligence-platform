"""data handling hardening: engagement purge columns + source_file purge column

Revision ID: b7e4d82f1c3a
Revises: a1c4e2f09b7d
Create Date: 2026-10-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b7e4d82f1c3a'
down_revision: Union[str, None] = 'a1c4e2f09b7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No raw_row column-type change: encryption and soft-purge redaction both
    # store a plain dict ({"_encrypted": ...} / {"_purged": true}) into the
    # existing JSON column — see app/services/encryption.py and
    # app/routers/data_purge.py.
    op.add_column('engagement', sa.Column('data_purged_at', sa.DateTime(), nullable=True))
    op.add_column('engagement', sa.Column('data_purged_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_engagement_data_purged_by_app_user', 'engagement', 'app_user', ['data_purged_by'], ['id']
    )
    op.add_column('source_file', sa.Column('content_purged_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('source_file', 'content_purged_at')

    op.drop_constraint('fk_engagement_data_purged_by_app_user', 'engagement', type_='foreignkey')
    op.drop_column('engagement', 'data_purged_by')
    op.drop_column('engagement', 'data_purged_at')
