from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID

from app.services.controls.base import ControlFinding, ControlResult, InvalidControlParameters

CONTROL_CODE = "round_number_transfers"
CONTROL_VERSION = 1

REQUIRED_PARAMETERS = ("round_to", "currency")


class _RecordLike(Protocol):
    id: UUID
    supplier_name: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: object


@dataclass(frozen=True)
class Parameters:
    round_to: Decimal
    currency: str


def parse_parameters(raw: dict | None) -> Parameters:
    """No safe default, same reasoning as threshold_splitting: what counts as
    "suspiciously round" (nearest ₦1,000 vs ₦100,000) is a judgment call about this
    firm's normal transaction sizes, not something this platform can guess without
    making an unsupported claim. The caller must supply both every run."""
    raw = raw or {}
    missing = [k for k in REQUIRED_PARAMETERS if raw.get(k) in (None, "")]
    if missing:
        raise InvalidControlParameters(
            f"round_number_transfers requires parameters: {list(REQUIRED_PARAMETERS)}. Missing: {missing}"
        )

    try:
        round_to = Decimal(str(raw["round_to"])).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise InvalidControlParameters("round_to must be a decimal number") from exc
    if round_to <= 0:
        raise InvalidControlParameters("round_to must be greater than zero")

    currency = str(raw["currency"]).strip().upper()
    if not currency:
        raise InvalidControlParameters("currency must not be empty")

    return Parameters(round_to=round_to, currency=currency)


def run(records: list[_RecordLike], parameters: dict | None = None) -> ControlResult:
    """Flags individual transactions whose amount is an exact multiple of the
    configured `round_to` unit. Round numbers are common in entirely legitimate
    business (rent, fixed fees, round contract values) — this is a deliberately
    low-confidence screening signal meant to be combined with other review steps,
    never treated as evidence of fabrication on its own. See
    docs/control-library.md."""
    params = parse_parameters(parameters)

    skipped = 0
    findings: list[ControlFinding] = []

    for record in records:
        if record.amount is None or not record.currency:
            skipped += 1
            continue
        if record.currency.strip().upper() != params.currency:
            # Different currency than configured — not comparable to this
            # round_to unit without an FX conversion this control does not perform.
            skipped += 1
            continue
        if record.amount <= 0:
            skipped += 1
            continue
        if record.amount % params.round_to != 0:
            continue

        findings.append(
            ControlFinding(
                severity="low",
                summary=(
                    f"Transaction to supplier '{record.supplier_name or '(no supplier recorded)'}' "
                    f"of {params.currency} {record.amount} on {record.transaction_date} is an exact "
                    f"multiple of {params.currency} {params.round_to}. Round-number amounts are common "
                    f"in legitimate business — this is a low-confidence screening signal, not evidence "
                    f"of a fabricated or estimated figure on its own."
                ),
                evidence_record_ids=[record.id],
            )
        )

    return ControlResult(findings=findings, skipped_row_count=skipped)
