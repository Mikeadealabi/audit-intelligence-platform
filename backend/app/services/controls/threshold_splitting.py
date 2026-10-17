from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID

from app.services.controls.base import ControlFinding, ControlResult, InvalidControlParameters

CONTROL_CODE = "threshold_splitting_candidates"
CONTROL_VERSION = 1

REQUIRED_PARAMETERS = ("threshold_amount", "currency", "window_days")


class _RecordLike(Protocol):
    id: UUID
    supplier_name: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: date | None


@dataclass(frozen=True)
class Parameters:
    threshold_amount: Decimal
    currency: str
    window_days: int


@dataclass(frozen=True)
class _Eligible:
    """A record that has passed the required-field and currency checks, with types
    narrowed so the clustering logic below never has to handle None."""

    id: UUID
    transaction_date: date
    amount: Decimal


def parse_parameters(raw: dict | None) -> Parameters:
    """This control has no safe default. The approval threshold a firm splits
    payments to dodge, and how many days apart still counts as "the same attempt,"
    are business/policy decisions — guessing at them would be exactly the kind of
    unsupported claim the brief forbids. The caller must supply them explicitly for
    every run; see docs/control-library.md."""
    raw = raw or {}
    missing = [k for k in REQUIRED_PARAMETERS if raw.get(k) in (None, "")]
    if missing:
        raise InvalidControlParameters(
            f"threshold_splitting_candidates requires parameters: {list(REQUIRED_PARAMETERS)}. "
            f"Missing: {missing}"
        )

    try:
        threshold_amount = Decimal(str(raw["threshold_amount"])).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise InvalidControlParameters("threshold_amount must be a decimal number") from exc
    if threshold_amount <= 0:
        raise InvalidControlParameters("threshold_amount must be greater than zero")

    currency = str(raw["currency"]).strip().upper()
    if not currency:
        raise InvalidControlParameters("currency must not be empty")

    try:
        window_days = int(raw["window_days"])
    except (TypeError, ValueError) as exc:
        raise InvalidControlParameters("window_days must be an integer") from exc
    if window_days < 1:
        raise InvalidControlParameters("window_days must be at least 1")

    return Parameters(threshold_amount=threshold_amount, currency=currency, window_days=window_days)


def run(records: list[_RecordLike], parameters: dict | None = None) -> ControlResult:
    """Flags clusters of sub-threshold transactions to the same supplier, close
    enough together in time, that together exceed the configured approval
    threshold. See docs/control-library.md for the clustering algorithm,
    assumptions, and limitations — this is a candidate for review, not proof of
    deliberate splitting."""
    params = parse_parameters(parameters)

    skipped = 0
    eligible_by_supplier: dict[str, list[_Eligible]] = defaultdict(list)

    for record in records:
        if not record.supplier_name or not record.currency or record.amount is None or record.transaction_date is None:
            skipped += 1
            continue
        if record.currency.strip().upper() != params.currency:
            # The threshold is defined in a single currency; amounts in other
            # currencies cannot be summed against it without an FX conversion this
            # control does not perform.
            skipped += 1
            continue
        if record.amount >= params.threshold_amount:
            # Only sub-threshold transactions are candidates for "splitting" —
            # a single transaction already at or above the threshold went through
            # whatever approval the threshold requires.
            continue
        eligible_by_supplier[record.supplier_name.strip().lower()].append(
            _Eligible(id=record.id, transaction_date=record.transaction_date, amount=record.amount)
        )

    findings: list[ControlFinding] = []
    for supplier, supplier_records in eligible_by_supplier.items():
        supplier_records.sort(key=lambda r: r.transaction_date)
        cluster: list[_Eligible] = []
        for elig in supplier_records:
            if cluster and (elig.transaction_date - cluster[-1].transaction_date).days > params.window_days:
                findings.extend(_flag_if_over_threshold(supplier, cluster, params))
                cluster = []
            cluster.append(elig)
        findings.extend(_flag_if_over_threshold(supplier, cluster, params))

    return ControlResult(findings=findings, skipped_row_count=skipped)


def _flag_if_over_threshold(supplier: str, cluster: list[_Eligible], params: Parameters) -> list[ControlFinding]:
    if len(cluster) < 2:
        return []
    total = sum((r.amount for r in cluster), Decimal("0"))
    if total < params.threshold_amount:
        return []

    first_date = min(r.transaction_date for r in cluster)
    last_date = max(r.transaction_date for r in cluster)
    return [
        ControlFinding(
            severity="high",
            summary=(
                f"{len(cluster)} sub-threshold transactions to supplier '{supplier}' "
                f"between {first_date} and {last_date} sum to {params.currency} {total}, "
                f"at or above the configured threshold of {params.currency} "
                f"{params.threshold_amount}. Review for possible approval-threshold "
                f"splitting."
            ),
            evidence_record_ids=[r.id for r in cluster],
        )
    ]
