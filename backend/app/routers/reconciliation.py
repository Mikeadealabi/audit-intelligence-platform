import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import (
    DatasetVersion,
    ExternalRecord,
    ExternalRecordBatch,
    ReconciliationMatch,
    ReconciliationRun,
    TransactionRecord,
)
from app.routers.engagements import get_engagement_or_404
from app.schemas import (
    ExternalRecordOut,
    ReconciliationMatchOut,
    ReconciliationRunOut,
    ReconciliationRunRequest,
    TransactionRecordOut,
)
from app.services.reconciliation import UnsupportedReconciliationMethod, execute_reconciliation

router = APIRouter(prefix="/engagements/{engagement_id}/reconciliation-runs", tags=["reconciliation"])

_MAX_MATCH_LIMIT = 500


@router.post("", response_model=ReconciliationRunOut, status_code=status.HTTP_201_CREATED)
def run_reconciliation(
    engagement_id: uuid.UUID,
    body: ReconciliationRunRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ReconciliationRun:
    engagement = get_engagement_or_404(db, principal, engagement_id)

    dataset_version = db.execute(
        select(DatasetVersion).where(
            DatasetVersion.id == body.dataset_version_id,
            DatasetVersion.tenant_id == principal.tenant_id,
            DatasetVersion.engagement_id == engagement.id,
        )
    ).scalar_one_or_none()
    if dataset_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found")

    external_record_batch = db.execute(
        select(ExternalRecordBatch).where(
            ExternalRecordBatch.id == body.external_record_batch_id,
            ExternalRecordBatch.tenant_id == principal.tenant_id,
            ExternalRecordBatch.engagement_id == engagement.id,
        )
    ).scalar_one_or_none()
    if external_record_batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External record batch not found")

    try:
        reconciliation_run = execute_reconciliation(
            db,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            engagement=engagement,
            dataset_version=dataset_version,
            external_record_batch=external_record_batch,
            method=body.method,
            parameters=body.parameters,
        )
    except UnsupportedReconciliationMethod as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    return reconciliation_run


@router.get("/{reconciliation_run_id}", response_model=ReconciliationRunOut)
def get_reconciliation_run(
    engagement_id: uuid.UUID,
    reconciliation_run_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ReconciliationRun:
    engagement = get_engagement_or_404(db, principal, engagement_id)
    run = db.execute(
        select(ReconciliationRun).where(
            ReconciliationRun.id == reconciliation_run_id,
            ReconciliationRun.tenant_id == principal.tenant_id,
            ReconciliationRun.engagement_id == engagement.id,
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reconciliation run not found")
    return run


@router.get("/{reconciliation_run_id}/matches", response_model=list[ReconciliationMatchOut])
def list_reconciliation_matches(
    engagement_id: uuid.UUID,
    reconciliation_run_id: uuid.UUID,
    match_status: str | None = Query(default=None, description="Filter: matched|unmatched_transaction|unmatched_external"),
    limit: int = Query(default=200, ge=1, le=_MAX_MATCH_LIMIT),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[ReconciliationMatchOut]:
    engagement = get_engagement_or_404(db, principal, engagement_id)
    run = db.execute(
        select(ReconciliationRun).where(
            ReconciliationRun.id == reconciliation_run_id,
            ReconciliationRun.tenant_id == principal.tenant_id,
            ReconciliationRun.engagement_id == engagement.id,
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reconciliation run not found")

    query = select(ReconciliationMatch).where(
        ReconciliationMatch.tenant_id == principal.tenant_id,
        ReconciliationMatch.reconciliation_run_id == run.id,
    )
    if match_status:
        query = query.where(ReconciliationMatch.match_status == match_status)
    matches = list(db.execute(query.order_by(ReconciliationMatch.created_at).offset(offset).limit(limit)).scalars())

    tx_ids = {m.transaction_record_id for m in matches if m.transaction_record_id}
    ext_ids = {m.external_record_id for m in matches if m.external_record_id}
    tx_by_id = {
        r.id: r for r in db.execute(select(TransactionRecord).where(TransactionRecord.id.in_(tx_ids))).scalars()
    } if tx_ids else {}
    ext_by_id = {
        r.id: r for r in db.execute(select(ExternalRecord).where(ExternalRecord.id.in_(ext_ids))).scalars()
    } if ext_ids else {}

    results = []
    for m in matches:
        tx = tx_by_id.get(m.transaction_record_id) if m.transaction_record_id else None
        ext = ext_by_id.get(m.external_record_id) if m.external_record_id else None
        results.append(
            ReconciliationMatchOut(
                id=m.id,
                match_status=m.match_status,
                match_basis=m.match_basis,
                transaction_record=TransactionRecordOut.model_validate(tx) if tx else None,
                external_record=ExternalRecordOut.model_validate(ext) if ext else None,
                created_at=m.created_at,
            )
        )
    return results
