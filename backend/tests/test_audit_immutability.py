import pytest
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent
from app.services.audit import record_audit_event


def test_update_on_audit_event_is_rejected_by_db(db, make_principal):
    headers, user_id, tenant_id = make_principal()
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=user_id, event_type="test.event", payload={})
    db.commit()

    event = db.query(AuditEvent).filter_by(tenant_id=tenant_id).one()
    event.event_type = "tampered"
    with pytest.raises(DBAPIError, match="immutable"):
        db.commit()
    db.rollback()


def test_delete_on_audit_event_is_rejected_by_db(db, make_principal):
    headers, user_id, tenant_id = make_principal()
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=user_id, event_type="test.event", payload={})
    db.commit()

    event = db.query(AuditEvent).filter_by(tenant_id=tenant_id).one()
    db.delete(event)
    with pytest.raises(DBAPIError, match="immutable"):
        db.commit()
    db.rollback()
