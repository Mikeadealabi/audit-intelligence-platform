from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID

from app.services.controls.base import ControlFinding, ControlResult, InvalidControlParameters

CONTROL_CODE = "new_vendor_candidates"
CONTROL_VERSION = 1


class _RecordLike(Protocol):
    id: UUID
    supplier_name: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: object


@dataclass(frozen=True)
class Parameters:
    min_amount: Decimal | None
    currency: str | None


def parse_parameters(raw: dict | None) -> Parameters:
    """Whether a supplier is new to this engagement is a plain fact, not a policy
    choice — so unlike threshold_splitting, this control has a safe default: with no
    parameters it flags every transaction to a first-seen supplier. `min_amount` is
    an optional narrowing filter for firms that only want large first-time payments
    surfaced; it must be paired with the currency it's denominated in, same
    reasoning as threshold_splitting's currency requirement."""
    raw = raw or {}
    has_min_amount = raw.get("min_amount") not in (None, "")
    has_currency = raw.get("currency") not in (None, "")
    if has_min_amount != has_currency:
        raise InvalidControlParameters(
            "new_vendor_candidates: min_amount and currency must be supplied together, or neither"
        )
    if not has_min_amount:
        return Parameters(min_amount=None, currency=None)

    try:
        min_amount = Decimal(str(raw["min_amount"])).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise InvalidControlParameters("min_amount must be a decimal number") from exc
    if min_amount <= 0:
        raise InvalidControlParameters("min_amount must be greater than zero")

    currency = str(raw["currency"]).strip().upper()
    if not currency:
        raise InvalidControlParameters("currency must not be empty")

    return Parameters(min_amount=min_amount, currency=currency)


def run(
    records: list[_RecordLike],
    parameters: dict | None = None,
    *,
    history_supplier_names: frozenset[str] | None = None,
    has_prior_history: bool = True,
) -> ControlResult:
    """Flags transactions to a supplier with no prior transaction history anywhere
    else in this engagement — a candidate for verifying the vendor is real and
    legitimate ("ghost vendor" check), not proof that it isn't. `history_supplier_names`
    and `has_prior_history` are supplied by the caller (see
    app/services/control_execution.py), which alone has visibility across dataset
    versions; this module never queries the database itself.

    If `has_prior_history` is False (this is the engagement's first-ever committed
    dataset version), the control is a no-op: every supplier would be "new" by
    definition, which would flag 100% of transactions and tell a reviewer nothing.
    See docs/control-library.md."""
    params = parse_parameters(parameters)

    if not has_prior_history:
        return ControlResult(findings=[], skipped_row_count=len(records))

    history = history_supplier_names or frozenset()
    skipped = 0
    findings: list[ControlFinding] = []

    for record in records:
        if not record.supplier_name:
            skipped += 1
            continue

        key = record.supplier_name.strip().lower()
        if key in history:
            continue  # has prior history — not a new-vendor candidate

        if params.min_amount is not None:
            if record.amount is None or not record.currency:
                skipped += 1
                continue
            if record.currency.strip().upper() != params.currency:
                # Different currency than the configured filter — not eligible for
                # this run, but not an error either; same treatment as
                # threshold_splitting's cross-currency exclusion.
                continue
            if record.amount < params.min_amount:
                continue

        findings.append(
            ControlFinding(
                severity="medium" if params.min_amount is not None else "low",
                summary=(
                    f"First transaction recorded for supplier '{record.supplier_name}' "
                    f"in this engagement — {record.currency or '(no currency)'} "
                    f"{record.amount if record.amount is not None else '(no amount)'} "
                    f"on {record.transaction_date}. No prior transaction history for "
                    f"this supplier in earlier dataset versions of this engagement. "
                    f"Verify the vendor is real and legitimately onboarded (registration, "
                    f"banking details, prior relationship) before treating as routine — "
                    f"this is a candidate for review, not evidence of a fictitious vendor."
                ),
                evidence_record_ids=[record.id],
            )
        )

    return ControlResult(findings=findings, skipped_row_count=skipped)
