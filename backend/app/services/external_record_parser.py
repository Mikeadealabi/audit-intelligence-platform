import csv
import io

from app.services.csv_parser import CsvValidationError, ParsedRow, ParseResult, _parse_amount, _parse_date

REQUIRED_EXTERNAL_FIELDS = ("reference", "currency", "amount", "transaction_date")
OPTIONAL_EXTERNAL_FIELDS = ("counterparty_name",)


def parse_external_csv(
    raw_bytes: bytes,
    column_mapping: dict[str, str],
    *,
    max_rows: int,
    max_bytes: int,
) -> ParseResult:
    """Parses the second, independently-sourced side of a reconciliation (a bank
    or payment-gateway statement export). Deliberately a separate function from
    csv_parser.parse_csv rather than a parameterized generalization of it — the
    two schemas have different required fields (no supplier_name/invoice_reference
    here) and keeping them as two small, explicit functions is easier to read and
    change independently than one function branching on a field-spec argument.
    Shares the actual value-parsing logic (_parse_amount, _parse_date) so a decimal
    or date string parses identically on both sides of a reconciliation."""
    if len(raw_bytes) > max_bytes:
        raise CsvValidationError(f"File exceeds maximum allowed size of {max_bytes} bytes")

    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("File is not valid UTF-8 text") from exc

    reader = csv.DictReader(io.StringIO(text))
    header = list(reader.fieldnames or [])
    if not header:
        raise CsvValidationError("File has no header row")

    missing_mapped_columns = [
        source_col for source_col in column_mapping.values() if source_col not in header
    ]
    if missing_mapped_columns:
        raise CsvValidationError(
            f"Mapped source column(s) not found in file header: {missing_mapped_columns}"
        )

    rows: list[ParsedRow] = []
    for row_number, raw_row in enumerate(reader, start=1):
        if row_number > max_rows:
            raise CsvValidationError(f"File exceeds maximum allowed row count of {max_rows}")

        errors: list[str] = []
        mapped: dict = {}

        for canonical_field in REQUIRED_EXTERNAL_FIELDS:
            source_col = column_mapping.get(canonical_field)
            raw_value = (raw_row.get(source_col) or "").strip() if source_col else ""

            if canonical_field == "amount":
                parsed_amount = _parse_amount(raw_value)
                if parsed_amount is None:
                    errors.append(f"amount: could not parse '{raw_value}' as a decimal amount")
                mapped["amount"] = parsed_amount
            elif canonical_field == "transaction_date":
                parsed_date = _parse_date(raw_value)
                if parsed_date is None:
                    errors.append(f"transaction_date: could not parse '{raw_value}' as a date")
                mapped["transaction_date"] = parsed_date
            else:
                if raw_value == "":
                    errors.append(f"{canonical_field}: required field is empty")
                mapped[canonical_field] = raw_value or None

        for canonical_field in OPTIONAL_EXTERNAL_FIELDS:
            source_col = column_mapping.get(canonical_field)
            raw_value = (raw_row.get(source_col) or "").strip() if source_col else ""
            mapped[canonical_field] = raw_value or None

        rows.append(ParsedRow(row_number=row_number, mapped=mapped, errors=errors))

    return ParseResult(rows=rows, header=header)
