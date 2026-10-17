"""Raw SQL for DB-level constraints that SQLAlchemy's ORM metadata can't express
(e.g. triggers). Shared between the Alembic migration (production/dev DB) and
tests/conftest.py (test DB, built via Base.metadata.create_all rather than
migrations) so the two never drift apart."""

AUDIT_EVENT_IMMUTABILITY_SQL = [
    """
    CREATE OR REPLACE FUNCTION prevent_audit_event_mutation()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'audit_event rows are immutable: % is not allowed', TG_OP;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE TRIGGER audit_event_no_update
    BEFORE UPDATE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
    """,
    """
    CREATE TRIGGER audit_event_no_delete
    BEFORE DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
    """,
]
