from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DatasetVersion,
    Engagement,
    ExternalRecord,
    ExternalRecordBatch,
    ReconciliationMatch,
    ReconciliationRun,
    TransactionRecord,
)
from app.services.audit import record_audit_event

SUPPORTED_METHODS = ("exact_match",)

_BASIS_EXACT = "exact:amount+currency+reference"
_BASIS_AMBIGUOUS = "ambiguous_duplicate_key"
_BASIS_NO_COUNTERPART_TX = "no_matching_external_record"
_BASIS_NO_COUNTERPART_EXT = "no_matching_transaction_record"
_BASIS_MISSING_FIELD = "missing_required_field"


class UnsupportedReconciliationMethod(ValueError):
    """Raised for any `method` other than "exact_match". A future tolerance-based
    or fuzzy method (date-window, amount-within-fee-tolerance, partial-payment
    splitting) is deliberately not implemented yet — those are business-rule
    decisions this platform should not guess at; see docs/reconciliation.md.
    `ReconciliationRun.method`/`.parameters` already exist so adding one later is
    additive, not a schema change."""


@dataclass(frozen=True)
class _Key:
    currency: str
    reference: str
    amount: Decimal


def _tx_key(record: TransactionRecord) -> _Key | None:
    if not record.currency or not record.invoice_reference or record.amount is None:
        return None
    return _Key(
        currency=record.currency.strip().upper(),
        reference=record.invoice_reference.strip().lower(),
        amount=record.amount,
    )


def _ext_key(record: ExternalRecord) -> _Key | None:
    if not record.currency or not record.reference or record.amount is None:
        return None
    return _Key(currency=record.currency.strip().upper(), reference=record.reference.strip().lower(), amount=record.amount)


def execute_reconciliation(
    db: Session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    engagement: Engagement,
    dataset_version: DatasetVersion,
    external_record_batch: ExternalRecordBatch,
    method: str = "exact_match",
    parameters: dict | None = None,
) -> ReconciliationRun:
    """Matches a dataset_version's transaction_records against an
    external_record_batch's external_records. Only `method="exact_match"` is
    implemented: a transaction and an external record pair only when their
    (currency, reference, amount) key is unique on *both* sides — if the same key
    appears more than once on either side, every record sharing it is left
    unmatched with match_basis="ambiguous_duplicate_key" rather than guessing
    which pairs together. `parameters` is accepted now (for a future
    tolerance-based method) but unused by exact_match. Flushes but does not
    commit — the caller owns the transaction boundary, same convention as
    execute_control_run."""
    if method not in SUPPORTED_METHODS:
        raise UnsupportedReconciliationMethod(
            f"Unsupported reconciliation method '{method}'. Supported: {list(SUPPORTED_METHODS)}."
        )

    db.flush()  # see execute_control_run — autoflush=False, caller may have pending rows

    tx_records = list(
        db.execute(
            select(TransactionRecord).where(
                TransactionRecord.tenant_id == tenant_id,
                TransactionRecord.dataset_version_id == dataset_version.id,
            )
        ).scalars()
    )
    ext_records = list(
        db.execute(
            select(ExternalRecord).where(
                ExternalRecord.tenant_id == tenant_id,
                ExternalRecord.external_record_batch_id == external_record_batch.id,
            )
        ).scalars()
    )

    tx_by_key: dict[_Key, list[TransactionRecord]] = defaultdict(list)
    unmatched_rows: list[tuple[UUID | None, UUID | None, str, str]] = []  # (tx_id, ext_id, status, basis)

    for tx in tx_records:
        key = _tx_key(tx)
        if key is None:
            unmatched_rows.append((tx.id, None, "unmatched_transaction", _BASIS_MISSING_FIELD))
        else:
            tx_by_key[key].append(tx)

    ext_by_key: dict[_Key, list[ExternalRecord]] = defaultdict(list)
    for ext in ext_records:
        key = _ext_key(ext)
        if key is None:
            unmatched_rows.append((None, ext.id, "unmatched_external", _BASIS_MISSING_FIELD))
        else:
            ext_by_key[key].append(ext)

    matched_pairs: list[tuple[UUID, UUID]] = []
    all_keys = set(tx_by_key) | set(ext_by_key)
    for key in all_keys:
        tx_group = tx_by_key.get(key, [])
        ext_group = ext_by_key.get(key, [])

        if len(tx_group) == 1 and len(ext_group) == 1:
            matched_pairs.append((tx_group[0].id, ext_group[0].id))
        elif tx_group and ext_group:
            # Same key on both sides but not a clean 1:1 — don't guess a pairing.
            for tx in tx_group:
                unmatched_rows.append((tx.id, None, "unmatched_transaction", _BASIS_AMBIGUOUS))
            for ext in ext_group:
                unmatched_rows.append((None, ext.id, "unmatched_external", _BASIS_AMBIGUOUS))
        elif tx_group:
            for tx in tx_group:
                unmatched_rows.append((tx.id, None, "unmatched_transaction", _BASIS_NO_COUNTERPART_TX))
        else:
            for ext in ext_group:
                unmatched_rows.append((None, ext.id, "unmatched_external", _BASIS_NO_COUNTERPART_EXT))

    reconciliation_run = ReconciliationRun(
        tenant_id=tenant_id,
        engagement_id=engagement.id,
        dataset_version_id=dataset_version.id,
        external_record_batch_id=external_record_batch.id,
        method=method,
        status="completed",
        finished_at=datetime.now(UTC),
        run_by=user_id,
        matched_count=len(matched_pairs),
        unmatched_transaction_count=sum(1 for r in unmatched_rows if r[2] == "unmatched_transaction"),
        unmatched_external_count=sum(1 for r in unmatched_rows if r[2] == "unmatched_external"),
        parameters=parameters or {},
    )
    db.add(reconciliation_run)
    db.flush()

    for tx_id, ext_id in matched_pairs:
        db.add(
            ReconciliationMatch(
                tenant_id=tenant_id,
                engagement_id=engagement.id,
                reconciliation_run_id=reconciliation_run.id,
                transaction_record_id=tx_id,
                external_record_id=ext_id,
                match_status="matched",
                match_basis=_BASIS_EXACT,
            )
        )
    for unmatched_tx_id, unmatched_ext_id, unmatched_status, unmatched_basis in unmatched_rows:
        db.add(
            ReconciliationMatch(
                tenant_id=tenant_id,
                engagement_id=engagement.id,
                reconciliation_run_id=reconciliation_run.id,
                transaction_record_id=unmatched_tx_id,
                external_record_id=unmatched_ext_id,
                match_status=unmatched_status,
                match_basis=unmatched_basis,
            )
        )

    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        engagement_id=engagement.id,
        event_type="reconciliation.run_completed",
        payload={
            "reconciliation_run_id": str(reconciliation_run.id),
            "dataset_version_id": str(dataset_version.id),
            "external_record_batch_id": str(external_record_batch.id),
            "method": method,
            "matched_count": reconciliation_run.matched_count,
            "unmatched_transaction_count": reconciliation_run.unmatched_transaction_count,
            "unmatched_external_count": reconciliation_run.unmatched_external_count,
        },
    )

    return reconciliation_run
