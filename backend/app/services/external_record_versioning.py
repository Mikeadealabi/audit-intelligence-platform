import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ExternalRecord, ExternalRecordBatch, ImportRun
from app.services.csv_parser import ParseResult


def next_external_batch_version_number(db: Session, *, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> int:
    """A separate per-engagement sequence from dataset_version.version_number —
    the two sides of a reconciliation are independently versioned, since a firm
    may re-upload a corrected bank statement without re-uploading the ledger side,
    or vice versa."""
    current_max = db.execute(
        select(func.max(ExternalRecordBatch.version_number)).where(
            ExternalRecordBatch.tenant_id == tenant_id,
            ExternalRecordBatch.engagement_id == engagement_id,
        )
    ).scalar_one()
    return (current_max or 0) + 1


def commit_external_import_run(
    db: Session,
    *,
    import_run: ImportRun,
    parse_result: ParseResult,
    source_file_sha256: str,
    source_label: str,
    committed_by: uuid.UUID,
) -> ExternalRecordBatch:
    """Creates exactly one immutable ExternalRecordBatch plus its ExternalRecord
    rows — the external-record mirror of dataset_versioning.commit_import_run.
    Only rows that passed validation are persisted."""
    version_number = next_external_batch_version_number(
        db, tenant_id=import_run.tenant_id, engagement_id=import_run.engagement_id
    )

    batch = ExternalRecordBatch(
        tenant_id=import_run.tenant_id,
        engagement_id=import_run.engagement_id,
        import_run_id=import_run.id,
        source_label=source_label,
        version_number=version_number,
        source_file_sha256=source_file_sha256,
        mapping_snapshot=import_run.column_mapping,
        committed_by=committed_by,
    )
    db.add(batch)
    db.flush()  # assign batch.id

    for row in parse_result.valid_rows:
        db.add(
            ExternalRecord(
                tenant_id=import_run.tenant_id,
                engagement_id=import_run.engagement_id,
                external_record_batch_id=batch.id,
                source_row_number=row.row_number,
                counterparty_name=row.mapped.get("counterparty_name"),
                reference=row.mapped.get("reference"),
                currency=row.mapped.get("currency"),
                amount=row.mapped.get("amount"),
                transaction_date=row.mapped.get("transaction_date"),
                raw_row=_json_safe(row.mapped),
            )
        )

    return batch


def _json_safe(mapped: dict) -> dict:
    out = {}
    for k, v in mapped.items():
        out[k] = str(v) if v is not None else None
    return out
