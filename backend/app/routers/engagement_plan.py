import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import EngagementPlan
from app.routers.engagements import get_engagement_or_404
from app.schemas import EngagementPlanIn, EngagementPlanOut
from app.services.audit import record_audit_event

router = APIRouter(prefix="/engagements/{engagement_id}/plan", tags=["engagement-plan"])


def _get_plan(db: Session, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> EngagementPlan | None:
    return db.execute(
        select(EngagementPlan).where(
            EngagementPlan.tenant_id == tenant_id,
            EngagementPlan.engagement_id == engagement_id,
        )
    ).scalar_one_or_none()


def _to_out(plan: EngagementPlan | None) -> EngagementPlanOut:
    if plan is None:
        return EngagementPlanOut(
            materiality_amount=None,
            materiality_currency=None,
            scope_notes=None,
            risk_assessment=None,
            risk_rating=None,
            updated_by=None,
            updated_at=None,
        )
    return EngagementPlanOut(
        materiality_amount=plan.materiality_amount,
        materiality_currency=plan.materiality_currency,
        scope_notes=plan.scope_notes,
        risk_assessment=plan.risk_assessment,
        risk_rating=plan.risk_rating,
        updated_by=plan.updated_by,
        updated_at=plan.updated_at,
    )


@router.get("", response_model=EngagementPlanOut)
def get_engagement_plan(
    engagement_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> EngagementPlanOut:
    """No row exists until the first PUT — a GET from an unopened plan panel
    returns an all-null default rather than creating a phantom row and audit
    entry just from a page view."""
    get_engagement_or_404(db, principal, engagement_id)
    return _to_out(_get_plan(db, principal.tenant_id, engagement_id))


@router.put("", response_model=EngagementPlanOut)
def set_engagement_plan(
    engagement_id: uuid.UUID,
    body: EngagementPlanIn,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> EngagementPlanOut:
    engagement = get_engagement_or_404(db, principal, engagement_id)

    plan = _get_plan(db, principal.tenant_id, engagement.id)
    if plan is None:
        plan = EngagementPlan(
            tenant_id=principal.tenant_id,
            engagement_id=engagement.id,
            updated_by=principal.user_id,
        )
        db.add(plan)

    plan.materiality_amount = body.materiality_amount
    plan.materiality_currency = body.materiality_currency
    plan.scope_notes = body.scope_notes
    plan.risk_assessment = body.risk_assessment
    plan.risk_rating = body.risk_rating
    plan.updated_by = principal.user_id

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="engagement.plan_updated",
        payload={
            "materiality_amount": str(body.materiality_amount) if body.materiality_amount is not None else None,
            "materiality_currency": body.materiality_currency,
            "risk_rating": body.risk_rating,
        },
    )
    db.commit()

    return _to_out(plan)
