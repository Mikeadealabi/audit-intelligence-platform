import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.services.controls import round_number_transfers
from app.services.controls.base import InvalidControlParameters

PARAMS = {"round_to": "10000.00", "currency": "NGN"}


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
        amount=Decimal("500000.00"),
        transaction_date=date(2026, 3, 1),
    )
    defaults.update(kwargs)
    return FakeRecord(**defaults)


def test_missing_parameters_raises():
    with pytest.raises(InvalidControlParameters):
        round_number_transfers.run([_record()], parameters=None)


def test_missing_one_parameter_raises():
    with pytest.raises(InvalidControlParameters):
        round_number_transfers.run([_record()], parameters={"round_to": "10000.00"})


def test_round_multiple_is_flagged():
    record = _record(amount=Decimal("500000.00"))
    result = round_number_transfers.run([record], parameters=PARAMS)
    assert len(result.findings) == 1
    assert result.findings[0].evidence_record_ids == [record.id]
    assert result.findings[0].severity == "low"


def test_non_multiple_not_flagged():
    record = _record(amount=Decimal("500123.45"))
    result = round_number_transfers.run([record], parameters=PARAMS)
    assert result.findings == []


def test_wrong_currency_skipped_not_flagged():
    record = _record(amount=Decimal("500000.00"), currency="USD")
    result = round_number_transfers.run([record], parameters=PARAMS)
    assert result.findings == []
    assert result.skipped_row_count == 1


def test_missing_amount_skipped():
    record = _record(amount=None)
    result = round_number_transfers.run([record], parameters=PARAMS)
    assert result.findings == []
    assert result.skipped_row_count == 1


def test_zero_amount_not_flagged():
    record = _record(amount=Decimal("0.00"))
    result = round_number_transfers.run([record], parameters=PARAMS)
    assert result.findings == []


def test_round_to_must_be_positive():
    with pytest.raises(InvalidControlParameters):
        round_number_transfers.run([_record()], parameters={"round_to": "0", "currency": "NGN"})
