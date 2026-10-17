import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import AppUser, AuditEvent
from app.routers.engagements import get_engagement_or_404
from app.schemas import AuditEventOut

router = APIRouter(prefix="/engagements/{engagement_id}/activity", tags=["activity"])

_MAX_LIMIT = 200


@router.get("", response_model=list[AuditEventOut])
def list_activity(
    engagement_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    """Read-only view over the append-only, DB-trigger-protected audit_event
    table (see db_triggers.py) — nothing here can be edited or deleted."""
    engagement = get_engagement_or_404(db, principal, engagement_id)

    events = list(
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == principal.tenant_id, AuditEvent.engagement_id == engagement.id)
            .order_by(AuditEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).scalars()
    )

    actor_ids = {e.actor_user_id for e in events if e.actor_user_id is not None}
    actors = {
        u.id: u.email for u in db.execute(select(AppUser).where(AppUser.id.in_(actor_ids))).scalars()
    }

    return [
        AuditEventOut(
            id=e.id,
            event_type=e.event_type,
            actor_email=actors.get(e.actor_user_id) if e.actor_user_id else None,
            payload=e.payload,
            created_at=e.created_at,
        )
        for e in events
    ]
