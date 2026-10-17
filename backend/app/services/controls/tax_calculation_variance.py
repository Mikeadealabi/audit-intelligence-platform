from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID

from app.services.controls.base import ControlFinding, ControlResult, InvalidControlParameters

CONTROL_CODE = "tax_calculation_variance"
CONTROL_VERSION = 1

_HUNDRED = Decimal("100")


class _RecordLike(Protocol):
    id: UUID
    supplier_name: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: object
    tax_category: str | None
    recorded_vat_amount: Decimal | None
    recorded_wht_amount: Decimal | None


@dataclass(frozen=True)
class Parameters:
    vat_rate_percent: Decimal
    vat_exempt_categories: frozenset[str]
    wht_rates_by_category: dict[str, Decimal]
    tolerance_amount: Decimal


def parse_parameters(raw: dict | None) -> Parameters:
    """`vat_rate_percent` and `wht_rates_by_category` have no built-in default.
    Nigerian VAT/WHT rates are statutory facts that change over time and this
    platform is not a qualified authority on current tax law (see DECISIONS.md and
    docs/control-library.md's non-negotiable no-compliance-assertion rule) — baking
    in a specific percentage would be exactly the kind of unsupported claim the
    brief forbids. The caller supplies the rate(s) it believes currently apply, and
    this control only ever computes a *variance against that configured rate*, never
    a compliance verdict. `tolerance_amount` defaults to 0.01 — that is a rounding
    allowance (a math fact, matching this platform's NUMERIC(18,2) precision
    everywhere else), not a policy choice, so a small default is safe here."""
    raw = raw or {}
    if raw.get("vat_rate_percent") in (None, ""):
        raise InvalidControlParameters(
            "tax_calculation_variance requires parameter: vat_rate_percent — the VAT "
            "rate you believe currently applies, e.g. \"7.5\". This platform does not "
            "assume a rate; verify the current statutory rate yourself."
        )
    try:
        vat_rate_percent = Decimal(str(raw["vat_rate_percent"]))
    except InvalidOperation as exc:
        raise InvalidControlParameters("vat_rate_percent must be a decimal number") from exc
    if vat_rate_percent < 0:
        raise InvalidControlParameters("vat_rate_percent must not be negative")

    vat_exempt_categories = frozenset(str(c).strip().lower() for c in (raw.get("vat_exempt_categories") or []))

    wht_rates_raw = raw.get("wht_rates_by_category") or {}
    if not isinstance(wht_rates_raw, dict):
        raise InvalidControlParameters("wht_rates_by_category must be an object mapping category -> rate percent")
    wht_rates_by_category: dict[str, Decimal] = {}
    for category, rate in wht_rates_raw.items():
        try:
            wht_rates_by_category[str(category).strip().lower()] = Decimal(str(rate))
        except InvalidOperation as exc:
            raise InvalidControlParameters(f"wht_rates_by_category['{category}'] must be a decimal number") from exc

    try:
        tolerance_amount = Decimal(str(raw.get("tolerance_amount", "0.01"))).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise InvalidControlParameters("tolerance_amount must be a decimal number") from exc
    if tolerance_amount < 0:
        raise InvalidControlParameters("tolerance_amount must not be negative")

    return Parameters(
        vat_rate_percent=vat_rate_percent,
        vat_exempt_categories=vat_exempt_categories,
        wht_rates_by_category=wht_rates_by_category,
        tolerance_amount=tolerance_amount,
    )


def run(records: list[_RecordLike], parameters: dict | None = None) -> ControlResult:
    """Computes the VAT (and, where `tax_category` matches a configured rate, WHT)
    expected on each transaction at the caller-supplied rate(s), and compares it to
    the recorded tax amount on the same row (if the source file carried one).
    Never asserts a transaction is or isn't tax-compliant — only flags a computed
    variance, or the absence of any recorded figure to check against, as a
    candidate for a tax/finance professional to review. See
    docs/control-library.md."""
    params = parse_parameters(parameters)

    skipped = 0
    findings: list[ControlFinding] = []

    for record in records:
        if record.amount is None or not record.currency:
            skipped += 1
            continue

        category = (record.tax_category or "").strip().lower() or None

        if category not in params.vat_exempt_categories:
            expected_vat = (record.amount * params.vat_rate_percent / _HUNDRED).quantize(Decimal("0.01"))
            findings.extend(
                _check(
                    record,
                    label="VAT",
                    expected=expected_vat,
                    recorded=record.recorded_vat_amount,
                    tolerance=params.tolerance_amount,
                    rate_percent=params.vat_rate_percent,
                )
            )

        if category is not None and category in params.wht_rates_by_category:
            wht_rate = params.wht_rates_by_category[category]
            expected_wht = (record.amount * wht_rate / _HUNDRED).quantize(Decimal("0.01"))
            findings.extend(
                _check(
                    record,
                    label="WHT",
                    expected=expected_wht,
                    recorded=record.recorded_wht_amount,
                    tolerance=params.tolerance_amount,
                    rate_percent=wht_rate,
                )
            )

    return ControlResult(findings=findings, skipped_row_count=skipped)


def _check(
    record: _RecordLike,
    *,
    label: str,
    expected: Decimal,
    recorded: Decimal | None,
    tolerance: Decimal,
    rate_percent: Decimal,
) -> list[ControlFinding]:
    if recorded is None:
        return [
            ControlFinding(
                severity="low",
                summary=(
                    f"No recorded {label} amount on this transaction to verify against. "
                    f"At the configured rate ({rate_percent}%), expected {label} is "
                    f"approximately {expected}. This flags a coverage gap in the source "
                    f"data, not a confirmed miscalculation — this platform never fills in "
                    f"a tax amount itself."
                ),
                evidence_record_ids=[record.id],
            )
        ]

    diff = abs(Decimal(recorded) - expected)
    if diff <= tolerance:
        return []

    return [
        ControlFinding(
            severity="high",
            summary=(
                f"Recorded {label} of {recorded} differs from the expected {label} of "
                f"{expected} (at the configured rate of {rate_percent}%) by {diff}, beyond "
                f"the configured tolerance of {tolerance}. Candidate for review — verify the "
                f"applicable rate and category for this transaction with a qualified tax "
                f"professional before treating this as a confirmed filing error."
            ),
            evidence_record_ids=[record.id],
        )
    ]
