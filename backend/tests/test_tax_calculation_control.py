import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.services.controls import tax_calculation_variance
from app.services.controls.base import InvalidControlParameters


@dataclass
class FakeRecord:
    id: uuid.UUID
    supplier_name: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: date | None
    tax_category: str | None
    recorded_vat_amount: Decimal | None
    recorded_wht_amount: Decimal | None


def _record(**kwargs) -> FakeRecord:
    defaults = dict(
        id=uuid.uuid4(),
        supplier_name="Acme Ltd",
        currency="NGN",
        amount=Decimal("100000.00"),
        transaction_date=date(2026, 3, 1),
        tax_category=None,
        recorded_vat_amount=None,
        recorded_wht_amount=None,
    )
    defaults.update(kwargs)
    return FakeRecord(**defaults)


def test_missing_vat_rate_raises():
    with pytest.raises(InvalidControlParameters):
        tax_calculation_variance.run([_record()], parameters=None)


def test_vat_within_tolerance_no_finding():
    record = _record(amount=Decimal("100000.00"), recorded_vat_amount=Decimal("7500.00"))
    result = tax_calculation_variance.run([record], parameters={"vat_rate_percent": "7.5"})
    assert result.findings == []


def test_vat_mismatch_beyond_tolerance_flagged_high():
    record = _record(amount=Decimal("100000.00"), recorded_vat_amount=Decimal("5000.00"))
    result = tax_calculation_variance.run([record], parameters={"vat_rate_percent": "7.5"})
    assert len(result.findings) == 1
    assert result.findings[0].severity == "high"
    assert result.findings[0].evidence_record_ids == [record.id]


def test_missing_recorded_vat_flagged_low():
    record = _record(amount=Decimal("100000.00"), recorded_vat_amount=None)
    result = tax_calculation_variance.run([record], parameters={"vat_rate_percent": "7.5"})
    assert len(result.findings) == 1
    assert result.findings[0].severity == "low"


def test_vat_exempt_category_skips_vat_check():
    record = _record(tax_category="Exports", amount=Decimal("100000.00"), recorded_vat_amount=None)
    result = tax_calculation_variance.run(
        [record], parameters={"vat_rate_percent": "7.5", "vat_exempt_categories": ["exports"]}
    )
    assert result.findings == []


def test_wht_recognized_category_checked():
    record = _record(
        tax_category="services",
        amount=Decimal("100000.00"),
        recorded_vat_amount=Decimal("7500.00"),
        recorded_wht_amount=Decimal("5000.00"),
    )
    result = tax_calculation_variance.run(
        [record],
        parameters={"vat_rate_percent": "7.5", "wht_rates_by_category": {"services": "10"}},
    )
    assert len(result.findings) == 1
    assert result.findings[0].severity == "high"  # 10000 expected vs 5000 recorded


def test_wht_unrecognized_category_not_checked():
    record = _record(tax_category="miscellaneous", amount=Decimal("100000.00"), recorded_vat_amount=Decimal("7500.00"))
    result = tax_calculation_variance.run(
        [record],
        parameters={"vat_rate_percent": "7.5", "wht_rates_by_category": {"services": "10"}},
    )
    # VAT matched, no recorded WHT check attempted for an unrecognized category.
    assert result.findings == []


def test_missing_amount_or_currency_skipped():
    record = _record(amount=None)
    result = tax_calculation_variance.run([record], parameters={"vat_rate_percent": "7.5"})
    assert result.findings == []
    assert result.skipped_row_count == 1
