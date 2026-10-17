import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import Engagement
from app.schemas import EngagementCreate, EngagementOut
from app.services.audit import record_audit_event

router = APIRouter(prefix="/engagements", tags=["engagements"])


@router.post("", response_model=EngagementOut, status_code=status.HTTP_201_CREATED)
def create_engagement(
    body: EngagementCreate,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Engagement:
    engagement = Engagement(
        tenant_id=principal.tenant_id,
        name=body.name,
        client_name=body.client_name,
        created_by=principal.user_id,
    )
    db.add(engagement)
    db.flush()
    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="engagement.created",
        payload={"engagement_id": str(engagement.id)},
    )
    db.commit()
    return engagement


@router.get("", response_model=list[EngagementOut])
def list_engagements(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[Engagement]:
    return list(
        db.execute(
            select(Engagement).where(Engagement.tenant_id == principal.tenant_id)
        ).scalars()
    )


def get_engagement_or_404(db: Session, principal: Principal, engagement_id: uuid.UUID) -> Engagement:
    """Tenant filter is always part of the query, never applied after the fact —
    a cross-tenant ID returns 404, same as a nonexistent one, so existence can't be
    inferred from status code alone."""
    engagement = db.execute(
        select(Engagement).where(
            Engagement.id == engagement_id,
            Engagement.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if engagement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")
    return engagement


@router.get("/{engagement_id}", response_model=EngagementOut)
def get_engagement(
    engagement_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Engagement:
    return get_engagement_or_404(db, principal, engagement_id)
