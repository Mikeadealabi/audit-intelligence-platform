import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import Finding, TransactionRecord
from app.routers.engagements import get_engagement_or_404
from app.schemas import DispositionRequest, FindingOut, TransactionRecordOut
from app.services.audit import record_audit_event

router = APIRouter(prefix="/engagements/{engagement_id}/findings", tags=["findings"])


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


@router.get("", response_model=list[FindingOut])
def list_findings(
    engagement_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[Finding]:
    get_engagement_or_404(db, principal, engagement_id)
    return list(
        db.execute(
            select(Finding).where(
                Finding.tenant_id == principal.tenant_id,
                Finding.engagement_id == engagement_id,
            )
        ).scalars()
    )


@router.get("/{finding_id}", response_model=FindingOut)
def get_finding(
    engagement_id: uuid.UUID,
    finding_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Finding:
    get_engagement_or_404(db, principal, engagement_id)
    return _get_finding_or_404(db, principal, engagement_id, finding_id)


@router.get("/{finding_id}/evidence", response_model=list[TransactionRecordOut])
def get_finding_evidence(
    engagement_id: uuid.UUID,
    finding_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[TransactionRecord]:
    get_engagement_or_404(db, principal, engagement_id)
    finding = _get_finding_or_404(db, principal, engagement_id, finding_id)

    evidence_ids = [uuid.UUID(rid) for rid in finding.evidence_record_ids]
    return list(
        db.execute(
            select(TransactionRecord).where(
                TransactionRecord.tenant_id == principal.tenant_id,
                TransactionRecord.id.in_(evidence_ids),
            )
        ).scalars()
    )


@router.post("/{finding_id}/disposition", response_model=FindingOut)
def record_disposition(
    engagement_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: DispositionRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Finding:
    """A human reviewer's disposition. This never happens automatically and the
    model (once Phase 5 exists) cannot call this endpoint on a user's behalf."""
    get_engagement_or_404(db, principal, engagement_id)
    finding = _get_finding_or_404(db, principal, engagement_id, finding_id)

    previous_status = finding.status
    finding.status = body.status

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement_id,
        event_type="finding.disposition_recorded",
        payload={
            "finding_id": str(finding.id),
            "previous_status": previous_status,
            "new_status": finding.status,
            "rationale": body.rationale,
        },
    )
    db.commit()
    return finding
