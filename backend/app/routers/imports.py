import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import ImportRun, SourceFile
from app.routers.engagements import get_engagement_or_404
from app.schemas import AutoRunControlResultOut, CommitImportResponse, ImportPreviewResponse, ImportPreviewRow
from app.services.audit import record_audit_event
from app.services.control_automation import auto_run_configured_controls
from app.services.csv_parser import CsvValidationError, parse_csv
from app.services.dataset_versioning import commit_import_run, compute_sha256, source_file_storage_key
from app.storage.local import LocalFilesystemStorage

router = APIRouter(prefix="/engagements/{engagement_id}/imports", tags=["imports"])

_storage = LocalFilesystemStorage(settings.local_storage_dir)

SAMPLE_ROW_LIMIT = 20


@router.post("/preview", response_model=ImportPreviewResponse, status_code=status.HTTP_201_CREATED)
async def preview_import(
    engagement_id: uuid.UUID,
    file: UploadFile = File(...),
    column_mapping: str = Form(..., description="JSON object: canonical field -> source column name"),
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ImportPreviewResponse:
    engagement = get_engagement_or_404(db, principal, engagement_id)

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
        parse_result = parse_csv(
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
        original_filename=file.filename or "upload.csv",
        storage_path="",  # set after write, below
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
        event_type="import.preview_created",
        payload={
            "import_run_id": str(import_run.id),
            "source_file_id": str(source_file.id),
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


@router.post("/{import_run_id}/commit", response_model=CommitImportResponse)
def commit_import(
    engagement_id: uuid.UUID,
    import_run_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> CommitImportResponse:
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

    try:
        raw_bytes = _storage.read(
            source_file_storage_key(principal.tenant_id, engagement.id, source_file.id, source_file.original_filename)
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stored file is no longer available (engagement data may have been purged); refusing to commit",
        ) from exc
    if compute_sha256(raw_bytes) != source_file.sha256_hash:
        # The immutability guarantee this platform relies on no longer holds — fail
        # loudly rather than committing data that doesn't match its recorded hash.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stored file no longer matches its recorded hash; refusing to commit",
        )

    parse_result = parse_csv(
        raw_bytes,
        import_run.column_mapping,
        max_rows=settings.max_rows_per_import,
        max_bytes=settings.max_upload_bytes,
    )

    dataset_version = commit_import_run(
        db,
        import_run=import_run,
        parse_result=parse_result,
        source_file_sha256=source_file.sha256_hash,
        committed_by=principal.user_id,
    )
    import_run.status = "committed"

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="import.committed",
        payload={
            "import_run_id": str(import_run.id),
            "dataset_version_id": str(dataset_version.id),
            "version_number": dataset_version.version_number,
            "row_count": len(parse_result.valid_rows),
        },
    )

    # Auto-run any controls this engagement has configured for dataset-commit
    # triggering, in the same transaction as the commit itself. See
    # app/services/control_automation.py.
    auto_run_results = auto_run_configured_controls(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        engagement=engagement,
        dataset_version=dataset_version,
    )

    db.commit()

    return CommitImportResponse(
        dataset_version_id=dataset_version.id,
        version_number=dataset_version.version_number,
        row_count=len(parse_result.valid_rows),
        auto_run_control_results=[
            AutoRunControlResultOut(
                control_code=r.control_code,
                status=r.status,
                finding_count=r.finding_count,
                skip_reason=r.skip_reason,
            )
            for r in auto_run_results
        ],
    )
