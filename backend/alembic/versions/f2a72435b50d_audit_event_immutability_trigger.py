"""audit_event immutability trigger

Revision ID: f2a72435b50d
Revises: 89b7aca8e13d
Create Date: 2026-10-17 01:26:44.893090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db_triggers import AUDIT_EVENT_IMMUTABILITY_SQL

revision: str = 'f2a72435b50d'
down_revision: Union[str, None] = '89b7aca8e13d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Closes a documented gap (docs/threat-model.md T4): the application layer never
    # exposes an update/delete route for audit_event, but that alone doesn't stop a
    # direct DB connection or a future bug from mutating history. Enforce it at the
    # database level too. SQL lives in app/db_triggers.py, shared with the test DB
    # setup in tests/conftest.py so the two can't drift apart.
    for statement in AUDIT_EVENT_IMMUTABILITY_SQL:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_update ON audit_event;")
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_delete ON audit_event;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_event_mutation();")
