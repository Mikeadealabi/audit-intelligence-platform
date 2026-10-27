import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal, require_admin
from app.models import Finding, TransactionRecord
from app.routers.engagements import get_engagement_or_404
from app.schemas import DispositionRequest, FindingOut, SignOffRequest, TransactionRecordOut
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
    # Every (re-)disposition queues the finding for review again — this covers
    # the first disposition and re-disposing after a sign-off rejection alike.
    finding.sign_off_status = "pending_review"
    # Who prepared this disposition — record_sign_off uses this to enforce a real
    # second person reviews it, not just an admin-role check.
    finding.disposition_recorded_by = principal.user_id

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


@router.post("/{finding_id}/sign-off", response_model=FindingOut)
def record_sign_off(
    engagement_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: SignOffRequest,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Finding:
    """A second-person review of an existing disposition. Gated by require_admin,
    and — now that a teammate/invite flow exists (see app/routers/invites.py) —
    actually enforced to require a different person than whoever recorded the
    disposition being reviewed, via `finding.disposition_recorded_by`. A finding
    dispositioned before that column existed has it as NULL, which skips the
    check (a documented transitional gap for pre-existing data, not a loophole;
    see DECISIONS.md)."""
    get_engagement_or_404(db, principal, engagement_id)
    finding = _get_finding_or_404(db, principal, engagement_id, finding_id)

    if finding.status == "open":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Finding has no disposition to review yet."
        )
    if finding.sign_off_status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Finding is not pending review (current sign-off status: {finding.sign_off_status}).",
        )
    if finding.disposition_recorded_by == principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot sign off a disposition you recorded yourself — ask another admin to review it.",
        )

    previous_sign_off_status = finding.sign_off_status
    if body.decision == "approve":
        finding.sign_off_status = "signed_off"
        finding.signed_off_by = principal.user_id
        finding.signed_off_at = datetime.now(UTC)
    else:
        finding.sign_off_status = "rejected"
        finding.signed_off_by = None
        finding.signed_off_at = None

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement_id,
        event_type="finding.signed_off" if body.decision == "approve" else "finding.signoff_rejected",
        payload={
            "finding_id": str(finding.id),
            "decision": body.decision,
            "comment": body.comment,
            "previous_sign_off_status": previous_sign_off_status,
        },
    )
    db.commit()
    return finding
