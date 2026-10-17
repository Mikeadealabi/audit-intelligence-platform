import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlRun, Finding, SourceFile, TransactionRecord
from app.services.llm.provider import ToolExecutionResult

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "get_finding_context",
        "description": (
            "Get the finding under investigation: its severity, status, summary, "
            "which control produced it, and the evidence record IDs it cites. "
            "Read-only."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"finding_id": {"type": "string"}},
            "required": ["finding_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_transaction_records",
        "description": (
            "Fetch specific transaction records by ID (supplier, invoice reference, "
            "currency, amount, date). Capped at a server-enforced maximum per call. "
            "Read-only — never returns raw uploaded file content."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"record_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["record_ids"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_invoice_candidates",
        "description": (
            "Given one transaction record ID, find other records in the same "
            "dataset version sharing the same supplier and invoice reference — "
            "useful for checking whether a flagged duplicate has further matches. "
            "Read-only."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "candidate_limit": {"type": "integer"},
            },
            "required": ["invoice_id", "candidate_limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_approval_against_policy",
        "description": (
            "Check a transaction against a versioned approval policy. NOTE: no "
            "approval-policy data exists in this build — this tool always reports "
            "itself unsupported rather than fabricating a compliance result. It is "
            "exposed now so the contract is stable once policy data exists."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction_id": {"type": "string"},
                "policy_version_id": {"type": ["string", "null"]},
            },
            "required": ["transaction_id", "policy_version_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_document_metadata",
        "description": (
            "Get metadata (filename, hash, size, content type, upload date) for "
            "uploaded source files by ID. Never returns file content. Read-only."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"document_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["document_ids"],
            "additionalProperties": False,
        },
    },
]


def make_tool_executor(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    dataset_version_id: uuid.UUID,
    max_records: int,
):
    """Returns a callable dispatching by tool name. Every query is scoped to the
    tenant/engagement/dataset of the finding under investigation — the model
    cannot widen its own scope by passing a different ID; it will just get an
    empty or error result, never another tenant's data."""

    def _get_finding_context(args: dict) -> ToolExecutionResult:
        finding_id = _parse_uuid(args.get("finding_id"))
        if finding_id is None:
            return _bad_argument("finding_id must be a UUID")

        finding = db.execute(
            select(Finding).where(
                Finding.id == finding_id,
                Finding.tenant_id == tenant_id,
                Finding.engagement_id == engagement_id,
            )
        ).scalar_one_or_none()
        if finding is None:
            return ToolExecutionResult(content={"error": "finding not found"}, summary="finding not found", is_error=True)

        control_run = db.get(ControlRun, finding.control_run_id)

        content = {
            "id": str(finding.id),
            "severity": finding.severity,
            "status": finding.status,
            "summary": finding.summary,
            "evidence_record_ids": finding.evidence_record_ids,
            "control_run_id": str(finding.control_run_id),
            "control_run_parameters": control_run.parameters if control_run else {},
        }
        return ToolExecutionResult(
            content=content,
            summary=f"finding {finding_id} ({finding.severity}, {len(finding.evidence_record_ids)} evidence ids)",
            evidence_ids=[str(rid) for rid in finding.evidence_record_ids],
        )

    def _get_transaction_records(args: dict) -> ToolExecutionResult:
        raw_ids = args.get("record_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            return _bad_argument("record_ids must be a non-empty array")
        record_ids = [rid for rid in (_parse_uuid(r) for r in raw_ids[:max_records]) if rid is not None]
        if not record_ids:
            return _bad_argument("record_ids contained no valid UUIDs")

        records = list(
            db.execute(
                select(TransactionRecord).where(
                    TransactionRecord.tenant_id == tenant_id,
                    TransactionRecord.dataset_version_id == dataset_version_id,
                    TransactionRecord.id.in_(record_ids),
                )
            ).scalars()
        )
        content = [_record_to_dict(r) for r in records]
        return ToolExecutionResult(
            content=content,
            summary=f"returned {len(records)} of {len(record_ids)} requested record(s)",
            evidence_ids=[str(r.id) for r in records],
        )

    def _compare_invoice_candidates(args: dict) -> ToolExecutionResult:
        invoice_id = _parse_uuid(args.get("invoice_id"))
        if invoice_id is None:
            return _bad_argument("invoice_id must be a UUID")
        limit = args.get("candidate_limit")
        if not isinstance(limit, int) or limit < 1:
            limit = 10
        limit = min(limit, max_records)

        anchor = db.execute(
            select(TransactionRecord).where(
                TransactionRecord.id == invoice_id,
                TransactionRecord.tenant_id == tenant_id,
                TransactionRecord.dataset_version_id == dataset_version_id,
            )
        ).scalar_one_or_none()
        if anchor is None or not anchor.supplier_name or not anchor.invoice_reference:
            return ToolExecutionResult(
                content={"error": "invoice record not found or missing supplier/invoice reference"},
                summary="invoice record not found",
                is_error=True,
            )

        candidates = list(
            db.execute(
                select(TransactionRecord)
                .where(
                    TransactionRecord.tenant_id == tenant_id,
                    TransactionRecord.dataset_version_id == dataset_version_id,
                    TransactionRecord.id != anchor.id,
                    TransactionRecord.supplier_name.isnot(None),
                    TransactionRecord.invoice_reference.isnot(None),
                )
                .limit(limit * 5)  # over-fetch, then filter case/whitespace-insensitively in Python
            ).scalars()
        )
        supplier_key = anchor.supplier_name.strip().lower()
        invoice_key = anchor.invoice_reference.strip().lower()
        matches = [c for c in candidates if _matches_key(c, supplier_key, invoice_key)][:limit]

        content = [_record_to_dict(r) for r in matches]
        return ToolExecutionResult(
            content=content,
            summary=f"found {len(matches)} candidate(s) matching invoice {invoice_id}",
            evidence_ids=[str(r.id) for r in matches],
        )

    def _check_approval_against_policy(_args: dict) -> ToolExecutionResult:
        content = {
            "supported": False,
            "reason": (
                "No approval-policy data exists for this engagement in this build. "
                "This is not a compliance result — do not treat it as pass or fail."
            ),
        }
        return ToolExecutionResult(content=content, summary="approval-policy check unsupported (no policy data)")

    def _get_document_metadata(args: dict) -> ToolExecutionResult:
        raw_ids = args.get("document_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            return _bad_argument("document_ids must be a non-empty array")
        doc_ids = [did for did in (_parse_uuid(r) for r in raw_ids[:max_records]) if did is not None]
        if not doc_ids:
            return _bad_argument("document_ids contained no valid UUIDs")

        files = list(
            db.execute(
                select(SourceFile).where(
                    SourceFile.tenant_id == tenant_id,
                    SourceFile.engagement_id == engagement_id,
                    SourceFile.id.in_(doc_ids),
                )
            ).scalars()
        )
        content = [
            {
                "id": str(f.id),
                "original_filename": f.original_filename,
                "sha256_hash": f.sha256_hash,
                "byte_size": f.byte_size,
                "content_type": f.content_type,
                "created_at": f.created_at.isoformat(),
            }
            for f in files
        ]
        return ToolExecutionResult(content=content, summary=f"returned metadata for {len(files)} document(s)")

    _DISPATCH = {
        "get_finding_context": _get_finding_context,
        "get_transaction_records": _get_transaction_records,
        "compare_invoice_candidates": _compare_invoice_candidates,
        "check_approval_against_policy": _check_approval_against_policy,
        "get_document_metadata": _get_document_metadata,
    }

    def executor(tool_name: str, arguments: dict) -> ToolExecutionResult:
        handler = _DISPATCH.get(tool_name)
        if handler is None:
            return ToolExecutionResult(content={"error": f"unknown tool '{tool_name}'"}, summary="unknown tool", is_error=True)
        return handler(arguments)

    return executor


def _matches_key(record: TransactionRecord, supplier_key: str, invoice_key: str) -> bool:
    if record.supplier_name is None or record.invoice_reference is None:
        return False
    return record.supplier_name.strip().lower() == supplier_key and record.invoice_reference.strip().lower() == invoice_key


def _record_to_dict(record: TransactionRecord) -> dict:
    return {
        "id": str(record.id),
        "source_row_number": record.source_row_number,
        "supplier_name": record.supplier_name,
        "invoice_reference": record.invoice_reference,
        "currency": record.currency,
        "amount": str(record.amount) if record.amount is not None else None,
        "transaction_date": record.transaction_date.isoformat() if record.transaction_date else None,
    }


def _parse_uuid(value: object) -> uuid.UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _bad_argument(message: str) -> ToolExecutionResult:
    return ToolExecutionResult(content={"error": message}, summary=f"bad argument: {message}", is_error=True)
