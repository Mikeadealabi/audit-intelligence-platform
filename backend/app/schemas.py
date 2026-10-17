import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)  # bcrypt's hard limit is 72 bytes
    tenant_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EngagementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client_name: str = Field(min_length=1, max_length=200)


class EngagementOut(BaseModel):
    id: uuid.UUID
    name: str
    client_name: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ColumnMapping(BaseModel):
    supplier_name: str
    invoice_reference: str
    currency: str
    amount: str
    transaction_date: str


class ImportPreviewRow(BaseModel):
    row_number: int
    mapped: dict
    errors: list[str]


class ImportPreviewResponse(BaseModel):
    import_run_id: uuid.UUID
    source_file_id: uuid.UUID
    total_rows: int
    valid_row_count: int
    error_row_count: int
    sample_rows: list[ImportPreviewRow]


class CommitImportResponse(BaseModel):
    dataset_version_id: uuid.UUID
    version_number: int
    row_count: int


class RunControlRequest(BaseModel):
    dataset_version_id: uuid.UUID
    control_code: str = "duplicate_invoice_candidates"
    parameters: dict | None = None


class FindingOut(BaseModel):
    id: uuid.UUID
    severity: str
    status: str
    summary: str
    evidence_record_ids: list[uuid.UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionRecordOut(BaseModel):
    id: uuid.UUID
    source_row_number: int
    supplier_name: str | None
    invoice_reference: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: date | None

    model_config = ConfigDict(from_attributes=True)


class ControlRunOut(BaseModel):
    id: uuid.UUID
    status: str
    finding_count: int
    skipped_row_count: int
    parameters: dict
    started_at: datetime
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DispositionRequest(BaseModel):
    status: str = Field(pattern="^(confirmed|false_positive|needs_more_evidence)$")
    rationale: str = Field(min_length=1, max_length=4000)


class ReportDispositionOut(BaseModel):
    status: str
    rationale: str
    recorded_at: datetime
    recorded_by: uuid.UUID | None


class ReportInvestigationOut(BaseModel):
    id: uuid.UUID
    model_id: str
    completed_at: datetime | None
    result: dict | None


class ReportFindingOut(BaseModel):
    id: uuid.UUID
    severity: str
    status: str
    summary: str
    evidence_record_ids: list[uuid.UUID]
    created_at: datetime
    control_code: str
    control_version: int
    dataset_version_number: int
    disposition: ReportDispositionOut | None
    latest_investigation: ReportInvestigationOut | None


class ReportControlRunOut(BaseModel):
    id: uuid.UUID
    control_code: str
    control_name: str
    control_version: int
    parameters: dict
    dataset_version_number: int
    finding_count: int
    skipped_row_count: int
    started_at: datetime
    finished_at: datetime | None


class ReportDatasetVersionOut(BaseModel):
    id: uuid.UUID
    version_number: int
    source_file_sha256: str
    mapping_snapshot: dict
    committed_at: datetime


class EngagementReport(BaseModel):
    engagement_id: uuid.UUID
    engagement_name: str
    client_name: str
    generated_at: datetime
    dataset_versions: list[ReportDatasetVersionOut]
    control_runs: list[ReportControlRunOut]
    findings: list[ReportFindingOut]
    limitations: list[str]


class InvestigationRunOut(BaseModel):
    id: uuid.UUID
    status: str
    model_id: str
    requested_at: datetime
    completed_at: datetime | None
    result: dict | None
    tool_call_log: list
    token_usage: dict
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)
