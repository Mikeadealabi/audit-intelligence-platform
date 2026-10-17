import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.services.controls import threshold_splitting
from app.services.controls.base import InvalidControlParameters

PARAMS = {"threshold_amount": "500000.00", "currency": "NGN", "window_days": 3}


@dataclass
class FakeRecord:
    id: uuid.UUID
    supplier_name: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: date | None


def _record(**kwargs) -> FakeRecord:
    defaults = dict(
        id=uuid.uuid4(),
        supplier_name="Acme Ltd",
        currency="NGN",
        amount=Decimal("200000.00"),
        transaction_date=date(2026, 3, 1),
    )
    defaults.update(kwargs)
    return FakeRecord(**defaults)


def test_missing_parameters_raises():
    with pytest.raises(InvalidControlParameters):
        threshold_splitting.run([_record()], parameters=None)


def test_missing_one_required_parameter_raises():
    with pytest.raises(InvalidControlParameters):
        threshold_splitting.run([_record()], parameters={"threshold_amount": "500000", "currency": "NGN"})


def test_zero_threshold_rejected():
    with pytest.raises(InvalidControlParameters):
        threshold_splitting.run([_record()], parameters={**PARAMS, "threshold_amount": "0"})


def test_two_subthreshold_transactions_summing_over_threshold_flagged():
    records = [
        _record(amount=Decimal("300000.00"), transaction_date=date(2026, 3, 1)),
        _record(amount=Decimal("300000.00"), transaction_date=date(2026, 3, 2)),
    ]
    result = threshold_splitting.run(records, PARAMS)
    assert len(result.findings) == 1
    assert len(result.findings[0].evidence_record_ids) == 2
    assert result.findings[0].severity == "high"


def test_transactions_outside_window_not_clustered_together():
    records = [
        _record(amount=Decimal("300000.00"), transaction_date=date(2026, 3, 1)),
        _record(amount=Decimal("300000.00"), transaction_date=date(2026, 3, 10)),  # 9 days later
    ]
    result = threshold_splitting.run(records, PARAMS)
    assert result.findings == []


def test_single_subthreshold_transaction_not_flagged():
    records = [_record(amount=Decimal("300000.00"))]
    result = threshold_splitting.run(records, PARAMS)
    assert result.findings == []


def test_subthreshold_transactions_not_summing_to_threshold_not_flagged():
    records = [
        _record(amount=Decimal("100000.00"), transaction_date=date(2026, 3, 1)),
        _record(amount=Decimal("100000.00"), transaction_date=date(2026, 3, 2)),
    ]
    result = threshold_splitting.run(records, PARAMS)
    assert result.findings == []


def test_single_transaction_at_or_above_threshold_not_flagged():
    records = [
        _record(amount=Decimal("600000.00"), transaction_date=date(2026, 3, 1)),
        _record(amount=Decimal("600000.00"), transaction_date=date(2026, 3, 2)),
    ]
    result = threshold_splitting.run(records, PARAMS)
    assert result.findings == []


def test_different_suppliers_not_clustered_together():
    records = [
        _record(supplier_name="Acme Ltd", amount=Decimal("300000.00"), transaction_date=date(2026, 3, 1)),
        _record(supplier_name="Globex Ltd", amount=Decimal("300000.00"), transaction_date=date(2026, 3, 1)),
    ]
    result = threshold_splitting.run(records, PARAMS)
    assert result.findings == []


def test_wrong_currency_excluded_and_counted_as_skipped():
    records = [
        _record(currency="USD", amount=Decimal("300000.00"), transaction_date=date(2026, 3, 1)),
        _record(currency="USD", amount=Decimal("300000.00"), transaction_date=date(2026, 3, 2)),
    ]
    result = threshold_splitting.run(records, PARAMS)
    assert result.findings == []
    assert result.skipped_row_count == 2


def test_missing_required_field_counted_as_skipped():
    records = [_record(amount=None)]
    result = threshold_splitting.run(records, PARAMS)
    assert result.skipped_row_count == 1


def test_three_way_chain_within_window_clusters_transitively():
    # Day 1 -> day 3 (gap 2, within window) -> day 6 (gap 3, within window from day 3)
    # even though day 1 to day 6 is a 5-day span, wider than window_days=3.
    records = [
        _record(amount=Decimal("200000.00"), transaction_date=date(2026, 3, 1)),
        _record(amount=Decimal("200000.00"), transaction_date=date(2026, 3, 3)),
        _record(amount=Decimal("200000.00"), transaction_date=date(2026, 3, 6)),
    ]
    result = threshold_splitting.run(records, PARAMS)
    assert len(result.findings) == 1
    assert len(result.findings[0].evidence_record_ids) == 3


def test_two_separate_clusters_for_same_supplier_both_flagged():
    records = [
        _record(amount=Decimal("300000.00"), transaction_date=date(2026, 3, 1)),
        _record(amount=Decimal("300000.00"), transaction_date=date(2026, 3, 2)),
        # gap of 10 days starts a new cluster
        _record(amount=Decimal("300000.00"), transaction_date=date(2026, 3, 12)),
        _record(amount=Decimal("300000.00"), transaction_date=date(2026, 3, 13)),
    ]
    result = threshold_splitting.run(records, PARAMS)
    assert len(result.findings) == 2
