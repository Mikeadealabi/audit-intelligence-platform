import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import Principal, get_current_principal, get_llm_provider
from app.models import ControlRun, Finding, InvestigationRun
from app.routers.engagements import get_engagement_or_404
from app.schemas import InvestigationRunOut
from app.services.audit import record_audit_event
from app.services.llm.orchestrator import run_investigation
from app.services.llm.provider import LLMProvider, ProviderError

router = APIRouter(prefix="/engagements/{engagement_id}/findings/{finding_id}/investigations", tags=["investigations"])


def _get_finding_or_404(db: Session, principal: Principal, engagement_id: uuid.UUID, finding_id: uuid.UUID) -> Finding:
    finding = db.execute(
        select(Finding).where(
            Finding.id == finding_id,
            Finding.tenant_id == principal.tenant_id,
            Finding.engagement_id == engagement_id,
        )
    ).scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return finding


@router.post("", response_model=InvestigationRunOut, status_code=status.HTTP_201_CREATED)
def request_investigation(
    engagement_id: uuid.UUID,
    finding_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
) -> InvestigationRun:
    engagement = get_engagement_or_404(db, principal, engagement_id)
    finding = _get_finding_or_404(db, principal, engagement_id, finding_id)

    since = datetime.now(UTC) - timedelta(days=1)
    recent_count = db.execute(
        select(func.count(InvestigationRun.id)).where(
            InvestigationRun.tenant_id == principal.tenant_id,
            InvestigationRun.requested_at >= since,
        )
    ).scalar_one()
    if recent_count >= settings.llm_max_investigations_per_tenant_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily investigation quota reached for this tenant. Try again tomorrow.",
        )

    control_run = db.execute(
        select(ControlRun).where(
            ControlRun.id == finding.control_run_id,
            ControlRun.tenant_id == principal.tenant_id,
        )
    ).scalar_one()

    investigation = InvestigationRun(
        tenant_id=principal.tenant_id,
        engagement_id=engagement.id,
        finding_id=finding.id,
        status="pending",
        model_id=settings.anthropic_model_id or "unknown",
        requested_by=principal.user_id,
    )
    db.add(investigation)
    db.flush()
    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="investigation.requested",
        payload={"investigation_run_id": str(investigation.id), "finding_id": str(finding.id)},
    )
    db.commit()

    try:
        result, tool_call_log, token_usage = run_investigation(
            db,
            provider=provider,
            tenant_id=principal.tenant_id,
            engagement_id=engagement.id,
            dataset_version_id=control_run.dataset_version_id,
            finding_id=finding.id,
        )
    except ProviderError as exc:
        investigation.status = "failed"
        investigation.error_message = str(exc)
        investigation.completed_at = datetime.now(UTC)
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            engagement_id=engagement.id,
            event_type="investigation.failed",
            payload={"investigation_run_id": str(investigation.id), "error": str(exc)},
        )
        db.commit()
        return investigation

    investigation.status = "completed"
    investigation.result = result.model_dump()
    investigation.tool_call_log = tool_call_log
    investigation.token_usage = token_usage
    investigation.completed_at = datetime.now(UTC)

    for call in tool_call_log:
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            engagement_id=engagement.id,
            event_type="llm_tool.invoked",
            payload={
                "investigation_run_id": str(investigation.id),
                "tool_name": call["tool_name"],
                "result_summary": call["result_summary"],
                "is_error": call["is_error"],
            },
        )
    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="investigation.completed",
        payload={
            "investigation_run_id": str(investigation.id),
            "tool_call_count": len(tool_call_log),
            "token_usage": token_usage,
        },
    )
    db.commit()
    return investigation


@router.get("", response_model=list[InvestigationRunOut])
def list_investigations(
    engagement_id: uuid.UUID,
    finding_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[InvestigationRun]:
    get_engagement_or_404(db, principal, engagement_id)
    _get_finding_or_404(db, principal, engagement_id, finding_id)
    return list(
        db.execute(
            select(InvestigationRun).where(
                InvestigationRun.tenant_id == principal.tenant_id,
                InvestigationRun.engagement_id == engagement_id,
                InvestigationRun.finding_id == finding_id,
            )
        ).scalars()
    )


@router.get("/{investigation_id}", response_model=InvestigationRunOut)
def get_investigation(
    engagement_id: uuid.UUID,
    finding_id: uuid.UUID,
    investigation_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> InvestigationRun:
    get_engagement_or_404(db, principal, engagement_id)
    _get_finding_or_404(db, principal, engagement_id, finding_id)
    investigation = db.execute(
        select(InvestigationRun).where(
            InvestigationRun.id == investigation_id,
            InvestigationRun.tenant_id == principal.tenant_id,
            InvestigationRun.engagement_id == engagement_id,
            InvestigationRun.finding_id == finding_id,
        )
    ).scalar_one_or_none()
    if investigation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    return investigation
