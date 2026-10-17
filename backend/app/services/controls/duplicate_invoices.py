from collections import defaultdict
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.services.controls.base import ControlFinding, ControlResult

CONTROL_CODE = "duplicate_invoice_candidates"
CONTROL_VERSION = 1


class _RecordLike(Protocol):
    id: UUID
    supplier_name: str | None
    invoice_reference: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: object


def run(records: list[_RecordLike], parameters: dict | None = None) -> ControlResult:
    """Groups records sharing supplier + invoice reference + currency + amount +
    date. Exact match only — see docs/control-library.md for documented
    limitations. Rows missing any required field are excluded, not guessed at.
    `parameters` is accepted for interface consistency with other controls (e.g.
    threshold_splitting) but is unused — this control takes no configuration."""

    groups: dict[tuple, list[_RecordLike]] = defaultdict(list)
    skipped = 0

    for record in records:
        key = _grouping_key(record)
        if key is None:
            skipped += 1
            continue
        groups[key].append(record)

    findings: list[ControlFinding] = []
    for (supplier, invoice_ref, currency, amount, txn_date), group in groups.items():
        if len(group) < 2:
            continue
        findings.append(
            ControlFinding(
                severity="medium",
                summary=(
                    f"{len(group)} records for supplier '{supplier}', invoice "
                    f"reference '{invoice_ref}', {currency} {amount}, dated "
                    f"{txn_date} share identical key fields. Review before "
                    f"treating as a confirmed duplicate."
                ),
                evidence_record_ids=[r.id for r in group],
            )
        )

    return ControlResult(findings=findings, skipped_row_count=skipped)


def _grouping_key(record: _RecordLike) -> tuple | None:
    if (
        not record.supplier_name
        or not record.invoice_reference
        or not record.currency
        or record.amount is None
        or not record.transaction_date
    ):
        return None

    return (
        record.supplier_name.strip().lower(),
        record.invoice_reference.strip().lower(),
        record.currency.strip().upper(),
        Decimal(record.amount),
        record.transaction_date,
    )
