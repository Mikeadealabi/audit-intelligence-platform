from decimal import Decimal

import pytest

from app.services.csv_parser import CsvValidationError, parse_csv

MAPPING = {
    "supplier_name": "Supplier",
    "invoice_reference": "InvoiceRef",
    "currency": "Currency",
    "amount": "Amount",
    "transaction_date": "Date",
}


def _csv(rows: list[str], header: str = "Supplier,InvoiceRef,Currency,Amount,Date") -> bytes:
    return ("\n".join([header, *rows])).encode("utf-8")


def test_parses_valid_rows():
    data = _csv(["Acme Ltd,INV-001,NGN,1000.00,2026-01-15"])
    result = parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)
    assert len(result.valid_rows) == 1
    row = result.valid_rows[0]
    assert row.mapped["amount"] == Decimal("1000.00")
    assert row.mapped["supplier_name"] == "Acme Ltd"


def test_amount_with_thousands_separator_parses():
    data = _csv(["Acme Ltd,INV-001,NGN,\"1,000.00\",2026-01-15"])
    result = parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)
    assert result.valid_rows[0].mapped["amount"] == Decimal("1000.00")


def test_decimal_precision_not_float_drift():
    data = _csv(["A,INV-1,NGN,100.10,2026-01-01", "A,INV-2,NGN,0.30,2026-01-01"])
    result = parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)
    total = sum((r.mapped["amount"] for r in result.valid_rows), Decimal("0"))
    assert total == Decimal("100.40")


def test_alternate_date_format_parses():
    data = _csv(["Acme,INV-1,NGN,1.00,15/01/2026"])
    result = parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)
    assert result.valid_rows[0].is_valid


def test_unparseable_amount_is_row_error_not_crash():
    data = _csv(["Acme,INV-1,NGN,not-a-number,2026-01-01"])
    result = parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)
    assert len(result.error_rows) == 1
    assert "amount" in result.error_rows[0].errors[0]


def test_unparseable_date_is_row_error_not_crash():
    data = _csv(["Acme,INV-1,NGN,1.00,not-a-date"])
    result = parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)
    assert len(result.error_rows) == 1


def test_missing_required_field_is_row_error():
    data = _csv([",INV-1,NGN,1.00,2026-01-01"])
    result = parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)
    assert len(result.error_rows) == 1
    assert "supplier_name" in result.error_rows[0].errors[0]


def test_empty_file_raises_file_level_error():
    with pytest.raises(CsvValidationError):
        parse_csv(b"", MAPPING, max_rows=100, max_bytes=10_000)


def test_missing_mapped_column_raises_file_level_error():
    data = _csv(["Acme,INV-1,NGN,1.00,2026-01-01"], header="Supplier,InvoiceRef,Currency,Amount")
    with pytest.raises(CsvValidationError):
        parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)


def test_oversized_file_rejected_before_parsing():
    data = _csv(["Acme,INV-1,NGN,1.00,2026-01-01"])
    with pytest.raises(CsvValidationError):
        parse_csv(data, MAPPING, max_rows=100, max_bytes=5)


def test_too_many_rows_rejected():
    data = _csv([f"Acme,INV-{i},NGN,1.00,2026-01-01" for i in range(5)])
    with pytest.raises(CsvValidationError):
        parse_csv(data, MAPPING, max_rows=2, max_bytes=10_000)


def test_bad_encoding_raises_file_level_error():
    data = b"Supplier,InvoiceRef,Currency,Amount,Date\n" + b"\xff\xfe\x00\x01,INV-1,NGN,1.00,2026-01-01"
    with pytest.raises(CsvValidationError):
        parse_csv(data, MAPPING, max_rows=100, max_bytes=10_000)
