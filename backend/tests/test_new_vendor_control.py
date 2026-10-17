import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.services.controls import new_vendor_candidates
from app.services.controls.base import InvalidControlParameters


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
        amount=Decimal("1000.00"),
        transaction_date=date(2026, 3, 1),
    )
    defaults.update(kwargs)
    return FakeRecord(**defaults)


def test_no_prior_history_at_all_is_a_no_op():
    # First-ever dataset version for the engagement: every supplier would be
    # "new" by definition — flagging all of them would say nothing useful.
    records = [_record(), _record(supplier_name="Zenith Ltd")]
    result = new_vendor_candidates.run(records, has_prior_history=False)
    assert result.findings == []
    assert result.skipped_row_count == len(records)


def test_supplier_not_in_history_is_flagged():
    record = _record(supplier_name="Brand New Supplier")
    result = new_vendor_candidates.run(
        [record], has_prior_history=True, history_supplier_names=frozenset({"acme ltd"})
    )
    assert len(result.findings) == 1
    assert result.findings[0].evidence_record_ids == [record.id]
    assert result.findings[0].severity == "low"


def test_supplier_in_history_case_and_whitespace_insensitive_not_flagged():
    record = _record(supplier_name="  Acme Ltd  ")
    result = new_vendor_candidates.run(
        [record], has_prior_history=True, history_supplier_names=frozenset({"acme ltd"})
    )
    assert result.findings == []


def test_missing_supplier_name_is_skipped():
    record = _record(supplier_name=None)
    result = new_vendor_candidates.run([record], has_prior_history=True, history_supplier_names=frozenset())
    assert result.findings == []
    assert result.skipped_row_count == 1


def test_min_amount_requires_currency_pair():
    with pytest.raises(InvalidControlParameters):
        new_vendor_candidates.run(
            [_record()], parameters={"min_amount": "500000.00"}, has_prior_history=True, history_supplier_names=frozenset()
        )


def test_min_amount_filter_excludes_small_new_vendor_payments():
    small = _record(supplier_name="New Co", amount=Decimal("1000.00"))
    large = _record(supplier_name="New Co", amount=Decimal("600000.00"))
    result = new_vendor_candidates.run(
        [small, large],
        parameters={"min_amount": "500000.00", "currency": "NGN"},
        has_prior_history=True,
        history_supplier_names=frozenset(),
    )
    assert len(result.findings) == 1
    assert result.findings[0].evidence_record_ids == [large.id]
    assert result.findings[0].severity == "medium"


def test_min_amount_filter_different_currency_not_flagged():
    record = _record(supplier_name="New Co", amount=Decimal("600000.00"), currency="USD")
    result = new_vendor_candidates.run(
        [record],
        parameters={"min_amount": "500000.00", "currency": "NGN"},
        has_prior_history=True,
        history_supplier_names=frozenset(),
    )
    assert result.findings == []
