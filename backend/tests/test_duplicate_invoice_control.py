import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.controls import duplicate_invoices


@dataclass
class FakeRecord:
    id: uuid.UUID
    supplier_name: str | None
    invoice_reference: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: date | None


def _record(**kwargs) -> FakeRecord:
    defaults = dict(
        id=uuid.uuid4(),
        supplier_name="Acme Ltd",
        invoice_reference="INV-001",
        currency="NGN",
        amount=Decimal("1000.00"),
        transaction_date=date(2026, 1, 15),
    )
    defaults.update(kwargs)
    return FakeRecord(**defaults)


def test_exact_duplicate_pair_produces_one_finding_with_both_ids():
    r1, r2 = _record(), _record()
    result = duplicate_invoices.run([r1, r2])
    assert len(result.findings) == 1
    assert set(result.findings[0].evidence_record_ids) == {r1.id, r2.id}
    assert result.skipped_row_count == 0


def test_three_way_duplicate_produces_one_finding_with_three_ids():
    records = [_record() for _ in range(3)]
    result = duplicate_invoices.run(records)
    assert len(result.findings) == 1
    assert len(result.findings[0].evidence_record_ids) == 3


def test_different_invoice_reference_no_finding():
    r1 = _record()
    r2 = _record(invoice_reference="INV-002")
    result = duplicate_invoices.run([r1, r2])
    assert result.findings == []


def test_different_currency_no_finding():
    r1 = _record()
    r2 = _record(currency="USD")
    result = duplicate_invoices.run([r1, r2])
    assert result.findings == []


def test_row_missing_amount_is_skipped_not_crashed():
    r1 = _record()
    r2 = _record(amount=None)
    result = duplicate_invoices.run([r1, r2])
    assert result.findings == []
    assert result.skipped_row_count == 1


def test_decimal_equality_not_float_drift():
    r1 = _record(amount=Decimal("100.10"))
    r2 = _record(amount=Decimal("100.10"))
    result = duplicate_invoices.run([r1, r2])
    assert len(result.findings) == 1


def test_supplier_name_case_and_whitespace_insensitive():
    r1 = _record(supplier_name="Acme Ltd")
    r2 = _record(supplier_name="  acme ltd  ")
    result = duplicate_invoices.run([r1, r2])
    assert len(result.findings) == 1


def test_single_record_no_finding():
    result = duplicate_invoices.run([_record()])
    assert result.findings == []


def test_empty_dataset_zero_findings_zero_skipped():
    result = duplicate_invoices.run([])
    assert result.findings == []
    assert result.skipped_row_count == 0
