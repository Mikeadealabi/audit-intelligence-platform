from dataclasses import dataclass
from uuid import UUID


class InvalidControlParameters(ValueError):
    """Raised when a control's required parameters are missing or malformed. The
    router turns this into a 400, not a 500 — bad configuration is a client error,
    not a server fault."""


@dataclass
class ControlFinding:
    severity: str
    summary: str
    evidence_record_ids: list[UUID]


@dataclass
class ControlResult:
    findings: list[ControlFinding]
    skipped_row_count: int
