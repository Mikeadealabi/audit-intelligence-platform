import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DatasetVersion, ImportRun, TransactionRecord
from app.services.csv_parser import ParseResult


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_file_storage_key(tenant_id: uuid.UUID, engagement_id: uuid.UUID, source_file_id: uuid.UUID, filename: str) -> str:
    # Server-generated only — never built from client-controlled path segments.
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-") or "upload.csv"
    return f"{tenant_id}/{engagement_id}/{source_file_id}/{safe_filename}"


def next_version_number(db: Session, *, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> int:
    current_max = db.execute(
        select(func.max(DatasetVersion.version_number)).where(
            DatasetVersion.tenant_id == tenant_id,
            DatasetVersion.engagement_id == engagement_id,
        )
    ).scalar_one()
    return (current_max or 0) + 1


def commit_import_run(
    db: Session,
    *,
    import_run: ImportRun,
    parse_result: ParseResult,
    source_file_sha256: str,
    committed_by: uuid.UUID,
) -> DatasetVersion:
    """Creates exactly one immutable DatasetVersion plus its TransactionRecord rows.
    Only rows that passed validation are persisted — invalid rows are rejected, never
    guessed at, and remain visible via import_run.validation_errors."""

    version_number = next_version_number(
        db, tenant_id=import_run.tenant_id, engagement_id=import_run.engagement_id
    )

    dataset_version = DatasetVersion(
        tenant_id=import_run.tenant_id,
        engagement_id=import_run.engagement_id,
        import_run_id=import_run.id,
        version_number=version_number,
        source_file_sha256=source_file_sha256,
        mapping_snapshot=import_run.column_mapping,
        committed_by=committed_by,
    )
    db.add(dataset_version)
    db.flush()  # assign dataset_version.id

    for row in parse_result.valid_rows:
        db.add(
            TransactionRecord(
                tenant_id=import_run.tenant_id,
                engagement_id=import_run.engagement_id,
                dataset_version_id=dataset_version.id,
                source_row_number=row.row_number,
                supplier_name=row.mapped.get("supplier_name"),
                invoice_reference=row.mapped.get("invoice_reference"),
                currency=row.mapped.get("currency"),
                amount=row.mapped.get("amount"),
                transaction_date=row.mapped.get("transaction_date"),
                tax_category=row.mapped.get("tax_category"),
                recorded_vat_amount=row.mapped.get("recorded_vat_amount"),
                recorded_wht_amount=row.mapped.get("recorded_wht_amount"),
                raw_row=_json_safe(row.mapped),
            )
        )

    return dataset_version


def _json_safe(mapped: dict) -> dict:
    out = {}
    for k, v in mapped.items():
        out[k] = str(v) if v is not None else None
    return out
