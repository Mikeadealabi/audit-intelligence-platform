import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

REQUIRED_CANONICAL_FIELDS = (
    "supplier_name",
    "invoice_reference",
    "currency",
    "amount",
    "transaction_date",
)

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


class CsvValidationError(Exception):
    """Raised for file-level problems that make the whole file unusable (too big,
    too many rows, unreadable encoding, missing header). Row-level problems do not
    raise — they are collected per row instead."""


@dataclass
class ParsedRow:
    row_number: int  # 1-based, matches the data row position (header excluded)
    mapped: dict
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    header: list[str]

    @property
    def valid_rows(self) -> list[ParsedRow]:
        return [r for r in self.rows if r.is_valid]

    @property
    def error_rows(self) -> list[ParsedRow]:
        return [r for r in self.rows if not r.is_valid]


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.strip().replace(",", "")
    if cleaned == "":
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _parse_date(raw: str) -> date | None:
    cleaned = raw.strip()
    if cleaned == "":
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_csv(
    raw_bytes: bytes,
    column_mapping: dict[str, str],
    *,
    max_rows: int,
    max_bytes: int,
) -> ParseResult:
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

        for canonical_field in REQUIRED_CANONICAL_FIELDS:
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

        rows.append(ParsedRow(row_number=row_number, mapped=mapped, errors=errors))

    return ParseResult(rows=rows, header=header)
