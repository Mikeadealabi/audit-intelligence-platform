import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.services.controls import benford_digit_analysis
from app.services.controls.base import InvalidControlParameters

# Counts proportional to Benford's expected leading-digit distribution for n=1000
# (round(1000 * expected_proportion[d])) — amounts are d * 10 so the leading
# digit is exactly d, with no rounding ambiguity.
_CONFORMING_COUNTS = {1: 301, 2: 176, 3: 125, 4: 97, 5: 79, 6: 67, 7: 58, 8: 51, 9: 46}

# Deliberately skewed: mostly leading digit 9, far from Benford's ~4.6% expectation.
_SKEWED_COUNTS = {1: 10, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 90}


@dataclass
class FakeRecord:
    id: uuid.UUID
    amount: Decimal | None


def _records_from_counts(counts: dict[int, int]) -> list[FakeRecord]:
    records = []
    for digit, count in counts.items():
        for _ in range(count):
            records.append(FakeRecord(id=uuid.uuid4(), amount=Decimal(digit * 10)))
    return records


def test_conforming_distribution_produces_no_finding():
    records = _records_from_counts(_CONFORMING_COUNTS)
    result = benford_digit_analysis.run(records, parameters=None)
    assert result.findings == []
    assert result.skipped_row_count == 0


def test_skewed_distribution_is_flagged():
    records = _records_from_counts(_SKEWED_COUNTS)
    result = benford_digit_analysis.run(records, parameters=None)
    assert len(result.findings) == 1
    assert result.findings[0].severity == "medium"
    assert len(result.findings[0].evidence_record_ids) == 100


def test_below_min_sample_size_is_a_no_op():
    records = _records_from_counts({9: 10})  # 10 records, default min_sample_size=100
    result = benford_digit_analysis.run(records, parameters=None)
    assert result.findings == []
    assert result.skipped_row_count == 10


def test_missing_amount_and_zero_amount_are_skipped():
    records = _records_from_counts(_CONFORMING_COUNTS)
    records.append(FakeRecord(id=uuid.uuid4(), amount=None))
    records.append(FakeRecord(id=uuid.uuid4(), amount=Decimal("0.00")))
    result = benford_digit_analysis.run(records, parameters=None)
    assert result.skipped_row_count == 2


def test_min_sample_size_below_30_rejected():
    with pytest.raises(InvalidControlParameters):
        benford_digit_analysis.run([], parameters={"min_sample_size": 10})


def test_min_sample_size_must_be_integer():
    with pytest.raises(InvalidControlParameters):
        benford_digit_analysis.run([], parameters={"min_sample_size": "not-a-number"})


def test_invalid_significance_level_rejected():
    records = _records_from_counts(_CONFORMING_COUNTS)
    with pytest.raises(InvalidControlParameters):
        benford_digit_analysis.run(records, parameters={"significance_level": "0.5"})


def test_custom_min_sample_size_allows_smaller_population():
    records = _records_from_counts({1: 15, 5: 15, 9: 10})  # 40 records
    result = benford_digit_analysis.run(records, parameters={"min_sample_size": 30})
    # Just confirms it actually runs the test instead of no-op'ing at n=40.
    assert result.skipped_row_count == 0
