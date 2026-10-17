import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import ExternalRecordBatch, ImportRun, SourceFile
from app.routers.engagements import get_engagement_or_404
from app.schemas import (
    CommitExternalImportResponse,
    ExternalRecordBatchOut,
    ImportPreviewResponse,
    ImportPreviewRow,
)
from app.services.audit import record_audit_event
from app.services.csv_parser import CsvValidationError
from app.services.dataset_versioning import compute_sha256, source_file_storage_key
from app.services.external_record_parser import parse_external_csv
from app.services.external_record_versioning import commit_external_import_run
from app.storage.local import LocalFilesystemStorage

router = APIRouter(prefix="/engagements/{engagement_id}/external-imports", tags=["external-imports"])

_storage = LocalFilesystemStorage(settings.local_storage_dir)

SAMPLE_ROW_LIMIT = 20


@router.post("/preview", response_model=ImportPreviewResponse, status_code=status.HTTP_201_CREATED)
async def preview_external_import(
    engagement_id: uuid.UUID,
    file: UploadFile = File(...),
    column_mapping: str = Form(..., description="JSON object: canonical field -> source column name"),
    source_label: str = Form(..., description="Free-text label for this source, e.g. 'GTBank NGN statement — Jan 2026'"),
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ImportPreviewResponse:
    """Preview for the reconciliation subsystem's second, independently-sourced
    data source (a bank/payment-gateway statement export) — the mirror of
    POST .../imports/preview for transaction_record. `source_label` is a plain
    caller-supplied label, never a real gateway/ERP connector identity; no such
    connector exists yet. See docs/reconciliation.md."""
    engagement = get_engagement_or_404(db, principal, engagement_id)

    if not source_label.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_label must not be empty")

    try:
        mapping = json.loads(column_mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="column_mapping is not valid JSON") from exc

    raw_bytes = await file.read()
    if len(raw_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.max_upload_bytes} bytes",
        )

    try:
        parse_result = parse_external_csv(
            raw_bytes,
            mapping,
            max_rows=settings.max_rows_per_import,
            max_bytes=settings.max_upload_bytes,
        )
    except CsvValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    sha256 = compute_sha256(raw_bytes)
    source_file = SourceFile(
        tenant_id=principal.tenant_id,
        engagement_id=engagement.id,
        uploaded_by=principal.user_id,
        original_filename=file.filename or "external.csv",
        storage_path="",
        sha256_hash=sha256,
        byte_size=len(raw_bytes),
        content_type=file.content_type or "text/csv",
    )
    db.add(source_file)
    db.flush()

    storage_key = source_file_storage_key(principal.tenant_id, engagement.id, source_file.id, source_file.original_filename)
    source_file.storage_path = _storage.write(storage_key, raw_bytes)

    import_run = ImportRun(
        tenant_id=principal.tenant_id,
        engagement_id=engagement.id,
        source_file_id=source_file.id,
        column_mapping=mapping,
        source_label=source_label.strip(),
        status="previewed",
        row_count=len(parse_result.rows),
        error_count=len(parse_result.error_rows),
        validation_errors={
            "rows": [
                {"row_number": r.row_number, "errors": r.errors} for r in parse_result.error_rows[:200]
            ]
        },
        created_by=principal.user_id,
    )
    db.add(import_run)
    db.flush()

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="external_import.preview_created",
        payload={
            "import_run_id": str(import_run.id),
            "source_file_id": str(source_file.id),
            "source_label": source_label.strip(),
            "sha256": sha256,
            "row_count": import_run.row_count,
            "error_count": import_run.error_count,
        },
    )
    db.commit()

    sample_rows = [
        ImportPreviewRow(
            row_number=r.row_number,
            mapped={k: (str(v) if v is not None else None) for k, v in r.mapped.items()},
            errors=r.errors,
        )
        for r in parse_result.rows[:SAMPLE_ROW_LIMIT]
    ]

    return ImportPreviewResponse(
        import_run_id=import_run.id,
        source_file_id=source_file.id,
        total_rows=import_run.row_count,
        valid_row_count=import_run.row_count - import_run.error_count,
        error_row_count=import_run.error_count,
        sample_rows=sample_rows,
    )


@router.post("/{import_run_id}/commit", response_model=CommitExternalImportResponse)
def commit_external_import(
    engagement_id: uuid.UUID,
    import_run_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> CommitExternalImportResponse:
    engagement = get_engagement_or_404(db, principal, engagement_id)

    import_run = db.execute(
        select(ImportRun).where(
            ImportRun.id == import_run_id,
            ImportRun.tenant_id == principal.tenant_id,
            ImportRun.engagement_id == engagement.id,
        )
    ).scalar_one_or_none()
    if import_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import run not found")
    if import_run.status != "previewed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Import run has status '{import_run.status}', expected 'previewed'. "
            "Committed imports cannot be committed again.",
        )

    source_file = db.execute(
        select(SourceFile).where(
            SourceFile.id == import_run.source_file_id,
            SourceFile.tenant_id == principal.tenant_id,
        )
    ).scalar_one()

    raw_bytes = _storage.read(
        source_file_storage_key(principal.tenant_id, engagement.id, source_file.id, source_file.original_filename)
    )
    if compute_sha256(raw_bytes) != source_file.sha256_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stored file no longer matches its recorded hash; refusing to commit",
        )

    parse_result = parse_external_csv(
        raw_bytes,
        import_run.column_mapping,
        max_rows=settings.max_rows_per_import,
        max_bytes=settings.max_upload_bytes,
    )

    batch = commit_external_import_run(
        db,
        import_run=import_run,
        parse_result=parse_result,
        source_file_sha256=source_file.sha256_hash,
        source_label=import_run.source_label or "",
        committed_by=principal.user_id,
    )
    import_run.status = "committed"

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="external_import.committed",
        payload={
            "import_run_id": str(import_run.id),
            "external_record_batch_id": str(batch.id),
            "version_number": batch.version_number,
            "row_count": len(parse_result.valid_rows),
        },
    )
    db.commit()

    return CommitExternalImportResponse(
        external_record_batch_id=batch.id,
        version_number=batch.version_number,
        row_count=len(parse_result.valid_rows),
    )


@router.get("/batches", response_model=list[ExternalRecordBatchOut])
def list_external_record_batches(
    engagement_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[ExternalRecordBatch]:
    engagement = get_engagement_or_404(db, principal, engagement_id)
    return list(
        db.execute(
            select(ExternalRecordBatch)
            .where(
                ExternalRecordBatch.tenant_id == principal.tenant_id,
                ExternalRecordBatch.engagement_id == engagement.id,
            )
            .order_by(ExternalRecordBatch.version_number.desc())
        ).scalars()
    )
