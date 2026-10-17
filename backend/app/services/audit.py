import uuid

from sqlalchemy.orm import Session

from app.models import AuditEvent

# Keys that must never land in an audit payload, even by accident.
_FORBIDDEN_PAYLOAD_KEYS = {"password", "password_hash", "token", "access_token", "raw_row"}


def record_audit_event(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    event_type: str,
    engagement_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    payload = payload or {}
    leaked = _FORBIDDEN_PAYLOAD_KEYS & payload.keys()
    if leaked:
        raise ValueError(f"Refusing to write audit event with forbidden keys: {leaked}")

    event = AuditEvent(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    return event
