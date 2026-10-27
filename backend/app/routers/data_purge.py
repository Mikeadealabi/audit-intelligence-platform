import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import Principal, require_admin
from app.models import ExternalRecord, SourceFile, TransactionRecord
from app.routers.engagements import get_engagement_or_404
from app.schemas import PurgeDataRequest, PurgeDataResponse
from app.services.audit import record_audit_event
from app.services.dataset_versioning import source_file_storage_key
from app.storage.local import LocalFilesystemStorage

router = APIRouter(prefix="/engagements/{engagement_id}", tags=["data-purge"])

_storage = LocalFilesystemStorage(settings.local_storage_dir)

_PURGED_RAW_ROW = {"_purged": True}


@router.post("/purge-data", response_model=PurgeDataResponse)
def purge_engagement_data(
    engagement_id: uuid.UUID,
    body: PurgeDataRequest,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PurgeDataResponse:
    """Soft purge: deletes raw uploaded file bytes and redacts raw_row content.
    Deliberately keeps canonical transaction fields, findings, dispositions,
    sign-offs, and the full audit trail intact — that evidence is the platform's
    core value and must survive a privacy-driven purge of raw source material.

    Always returns 200 and re-scans for newly-un-purged content on every call,
    rather than 409-ing once already_purged: an engagement stays active after a
    purge (more files can be uploaded later), so a hard one-shot 409 would make it
    impossible to ever purge data added after an earlier purge."""
    engagement = get_engagement_or_404(db, principal, engagement_id)

    if body.confirm_engagement_name != engagement.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm_engagement_name does not match this engagement's name",
        )

    already_purged = engagement.data_purged_at is not None

    source_files = list(
        db.execute(
            select(SourceFile).where(
                SourceFile.tenant_id == principal.tenant_id,
                SourceFile.engagement_id == engagement.id,
                SourceFile.content_purged_at.is_(None),
            )
        ).scalars()
    )
    now = datetime.now(UTC)
    for source_file in source_files:
        key = source_file_storage_key(
            principal.tenant_id, engagement.id, source_file.id, source_file.original_filename
        )
        _storage.delete(key)
        source_file.content_purged_at = now
    source_file_count = len(source_files)

    # Postgres's plain `json` column type has no equality operator, so
    # "not already purged" is filtered in Python, not pushed into the query —
    # matches how controls already load an engagement's records into memory.
    transaction_records = [
        r
        for r in db.execute(
            select(TransactionRecord).where(
                TransactionRecord.tenant_id == principal.tenant_id,
                TransactionRecord.engagement_id == engagement.id,
            )
        ).scalars()
        if r.raw_row != _PURGED_RAW_ROW
    ]
    for txn_record in transaction_records:
        txn_record.raw_row = _PURGED_RAW_ROW

    external_records = [
        r
        for r in db.execute(
            select(ExternalRecord).where(
                ExternalRecord.tenant_id == principal.tenant_id,
                ExternalRecord.engagement_id == engagement.id,
            )
        ).scalars()
        if r.raw_row != _PURGED_RAW_ROW
    ]
    for ext_record in external_records:
        ext_record.raw_row = _PURGED_RAW_ROW

    engagement.data_purged_at = now
    engagement.data_purged_by = principal.user_id

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="engagement.data_purged",
        payload={
            "source_file_count": source_file_count,
            "transaction_record_count": len(transaction_records),
            "external_record_count": len(external_records),
            "already_purged": already_purged,
        },
    )
    db.commit()

    return PurgeDataResponse(
        data_purged_at=engagement.data_purged_at,
        data_purged_by=engagement.data_purged_by,
        source_file_count=source_file_count,
        transaction_record_count=len(transaction_records),
        external_record_count=len(external_records),
        already_purged=already_purged,
    )
