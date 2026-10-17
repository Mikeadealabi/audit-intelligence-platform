import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.services.controls.base import ControlFinding, ControlResult, InvalidControlParameters

CONTROL_CODE = "benford_digit_analysis"
CONTROL_VERSION = 1

# Benford's Law: the expected frequency of leading digit d in naturally-occurring
# numeric data is log10(1 + 1/d) — a mathematical fact, not a policy choice, so
# (unlike an approval threshold or a "round" unit) it is never a parameter.
_EXPECTED_PROPORTION: dict[int, float] = {d: math.log10(1 + 1 / d) for d in range(1, 10)}

# Chi-square critical values for 8 degrees of freedom (9 leading digits, 1-9) at
# standard significance levels — a fixed statistical fact, not a policy choice.
_CHI_SQUARE_CRITICAL_VALUES: dict[Decimal, float] = {
    Decimal("0.10"): 13.362,
    Decimal("0.05"): 15.507,
    Decimal("0.01"): 20.090,
}

# Benford's Law is only statistically meaningful on a reasonably large sample.
# 100 is a commonly used practical lower bound in first-digit testing literature
# (some sources recommend higher, e.g. 300, for high confidence) — this is a
# documented methodological convention, not an absolute law, so it is overridable,
# but it is safe to default because it is a statistical fact about sample size,
# not a business/policy judgment.
_DEFAULT_MIN_SAMPLE_SIZE = 100
_DEFAULT_SIGNIFICANCE_LEVEL = Decimal("0.05")


class _RecordLike(Protocol):
    id: UUID
    amount: Decimal | None


@dataclass(frozen=True)
class Parameters:
    min_sample_size: int
    significance_level: Decimal


def parse_parameters(raw: dict | None) -> Parameters:
    """Both parameters have safe, documented defaults — they are statistical
    conventions (minimum sample size, confidence level), not business-policy
    judgments, so unlike threshold_splitting_candidates or round_number_transfers
    this control runs with no parameters at all."""
    raw = raw or {}

    min_sample_size = raw.get("min_sample_size", _DEFAULT_MIN_SAMPLE_SIZE)
    try:
        min_sample_size = int(min_sample_size)
    except (TypeError, ValueError) as exc:
        raise InvalidControlParameters("min_sample_size must be an integer") from exc
    if min_sample_size < 30:
        # Below ~30 samples, a first-digit chi-square test is not considered
        # meaningful by any commonly cited convention; refuse rather than produce
        # a statistically unsupportable finding.
        raise InvalidControlParameters("min_sample_size must be at least 30")

    significance_level = Decimal(str(raw.get("significance_level", _DEFAULT_SIGNIFICANCE_LEVEL)))
    if significance_level not in _CHI_SQUARE_CRITICAL_VALUES:
        raise InvalidControlParameters(
            f"significance_level must be one of {sorted(str(k) for k in _CHI_SQUARE_CRITICAL_VALUES)}"
        )

    return Parameters(min_sample_size=min_sample_size, significance_level=significance_level)


def _leading_digit(amount: Decimal) -> int | None:
    """First nonzero decimal digit of abs(amount), ignoring the decimal point.
    Returns None for a zero amount (no leading digit exists)."""
    digits = format(abs(amount), "f").replace(".", "").lstrip("0")
    if not digits:
        return None
    return int(digits[0])


def run(records: list[_RecordLike], parameters: dict | None = None) -> ControlResult:
    """Tests whether the leading-digit distribution of transaction amounts in this
    dataset_version deviates significantly from Benford's Law — a classic
    forensic-accounting screen for fabricated or estimated figures. Runs once over
    the whole dataset_version (not per-supplier): splitting into many small
    per-supplier populations would mostly fall below any meaningful sample size and
    would overstate the test's precision at that granularity — a documented
    limitation, see docs/control-library.md. A deviation is a statistical anomaly
    worth investigating, never proof of manipulation — plenty of legitimate
    populations (e.g. prices clustered at fixed price points) deviate from Benford's
    Law too, so this is always severity "medium"."""
    params = parse_parameters(parameters)

    digit_counts: dict[int, int] = {d: 0 for d in range(1, 10)}
    eligible_ids: list[UUID] = []
    skipped = 0

    for record in records:
        if record.amount is None:
            skipped += 1
            continue
        digit = _leading_digit(record.amount)
        if digit is None:
            skipped += 1
            continue
        digit_counts[digit] += 1
        eligible_ids.append(record.id)

    n = len(eligible_ids)
    if n < params.min_sample_size:
        # Too few eligible rows for the test to be statistically meaningful —
        # this is "couldn't check," not "no anomaly found." All records are
        # counted as skipped, same convention as new_vendor_candidates's
        # first-dataset-version no-op.
        return ControlResult(findings=[], skipped_row_count=len(records))

    chi_square = sum(
        ((digit_counts[d] - n * _EXPECTED_PROPORTION[d]) ** 2) / (n * _EXPECTED_PROPORTION[d]) for d in range(1, 10)
    )
    critical_value = _CHI_SQUARE_CRITICAL_VALUES[params.significance_level]

    if chi_square <= critical_value:
        return ControlResult(findings=[], skipped_row_count=skipped)

    observed_vs_expected = ", ".join(
        f"{d}: observed {digit_counts[d]} ({digit_counts[d] / n:.1%}), expected {_EXPECTED_PROPORTION[d]:.1%}"
        for d in range(1, 10)
    )
    confidence_pct = (Decimal("1") - params.significance_level) * 100
    finding = ControlFinding(
        severity="medium",
        summary=(
            f"Leading-digit distribution of {n} eligible transaction amounts in this dataset "
            f"deviates from Benford's Law at the {confidence_pct:.0f}% confidence level "
            f"(chi-square statistic {chi_square:.2f} > critical value {critical_value} at "
            f"significance level {params.significance_level}, 8 degrees of freedom). "
            f"Per-digit breakdown — {observed_vs_expected}. A statistical screening signal, not "
            f"proof of fabricated or manipulated figures — legitimate populations can also deviate "
            f"(e.g. fixed price points, rounded fee schedules). Candidate for further review, "
            f"such as investigating which suppliers or transaction types contribute most to the "
            f"deviation."
        ),
        evidence_record_ids=eligible_ids,
    )
    return ControlResult(findings=[finding], skipped_row_count=skipped)
