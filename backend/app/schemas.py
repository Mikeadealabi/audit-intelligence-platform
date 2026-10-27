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


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(member|admin)$")


class InviteCreateResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    token: str  # returned only here, once — never again
    invite_url: str
    expires_at: datetime


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str  # "pending" | "accepted" | "revoked" | "expired"
    created_at: datetime
    expires_at: datetime
    invited_by: uuid.UUID
    accepted_at: datetime | None


class InvitePreview(BaseModel):
    email: str
    role: str
    tenant_name: str


class AcceptInviteRequest(BaseModel):
    password: str = Field(min_length=10, max_length=72)


class TenantMemberOut(BaseModel):
    id: uuid.UUID  # membership id
    user_id: uuid.UUID
    email: str
    role: str
    created_at: datetime


class EngagementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client_name: str = Field(min_length=1, max_length=200)


class EngagementOut(BaseModel):
    id: uuid.UUID
    name: str
    client_name: str
    status: str
    created_at: datetime
    data_purged_at: datetime | None
    data_purged_by: uuid.UUID | None

    model_config = ConfigDict(from_attributes=True)


class PurgeDataRequest(BaseModel):
    confirm_engagement_name: str = Field(min_length=1, max_length=200)


class PurgeDataResponse(BaseModel):
    data_purged_at: datetime
    data_purged_by: uuid.UUID
    source_file_count: int
    transaction_record_count: int
    external_record_count: int
    already_purged: bool


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


class AutoRunControlResultOut(BaseModel):
    control_code: str
    status: str  # "completed" | "skipped"
    finding_count: int | None = None
    skip_reason: str | None = None


class CommitImportResponse(BaseModel):
    dataset_version_id: uuid.UUID
    version_number: int
    row_count: int
    auto_run_control_results: list[AutoRunControlResultOut] = []


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
    sign_off_status: str
    signed_off_by: uuid.UUID | None
    signed_off_at: datetime | None
    disposition_recorded_by: uuid.UUID | None
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


class SignOffRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    comment: str = Field(min_length=1, max_length=2000)


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
    data_purged_at: datetime | None
    data_purged_by: uuid.UUID | None
    dataset_versions: list[ReportDatasetVersionOut]
    control_runs: list[ReportControlRunOut]
    findings: list[ReportFindingOut]
    limitations: list[str]


class FindingsByControlOut(BaseModel):
    control_code: str
    control_name: str
    finding_count: int


class SupplierSummaryOut(BaseModel):
    supplier_name: str
    transaction_count: int
    total_amount_by_currency: dict[str, str]
    flagged_transaction_count: int


class SupplierRiskOut(BaseModel):
    supplier_name: str
    risk_score: int
    controls_hit: list[str]
    total_finding_count: int
    severity_breakdown: dict[str, int]


class EngagementAnalytics(BaseModel):
    dataset_version_id: uuid.UUID | None
    dataset_version_number: int | None
    findings_by_severity: dict[str, int]
    findings_by_status: dict[str, int]
    findings_by_control: list[FindingsByControlOut]
    supplier_summary: list[SupplierSummaryOut]
    supplier_risk_scores: list[SupplierRiskOut] = []


class ControlConfigurationIn(BaseModel):
    enabled: bool
    parameters: dict | None = None


class ControlConfigurationOut(BaseModel):
    control_code: str
    control_name: str
    description: str
    enabled: bool
    parameters: dict
    required_parameters_hint: list[str]
    updated_at: datetime | None


class EngagementPlanIn(BaseModel):
    materiality_amount: Decimal | None = None
    materiality_currency: str | None = Field(default=None, max_length=10)
    scope_notes: str | None = Field(default=None, max_length=4000)
    risk_assessment: str | None = Field(default=None, max_length=4000)
    risk_rating: str | None = Field(default=None, pattern="^(low|medium|high)$")


class EngagementPlanOut(BaseModel):
    materiality_amount: Decimal | None
    materiality_currency: str | None
    scope_notes: str | None
    risk_assessment: str | None
    risk_rating: str | None
    updated_by: uuid.UUID | None
    updated_at: datetime | None


class CommitExternalImportResponse(BaseModel):
    external_record_batch_id: uuid.UUID
    version_number: int
    row_count: int


class ExternalRecordBatchOut(BaseModel):
    id: uuid.UUID
    source_label: str
    version_number: int
    committed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExternalRecordOut(BaseModel):
    id: uuid.UUID
    source_row_number: int
    counterparty_name: str | None
    reference: str | None
    currency: str | None
    amount: Decimal | None
    transaction_date: date | None

    model_config = ConfigDict(from_attributes=True)


class ReconciliationRunRequest(BaseModel):
    dataset_version_id: uuid.UUID
    external_record_batch_id: uuid.UUID
    method: str = "exact_match"
    parameters: dict | None = None


class ReconciliationRunOut(BaseModel):
    id: uuid.UUID
    method: str
    status: str
    matched_count: int
    unmatched_transaction_count: int
    unmatched_external_count: int
    parameters: dict
    started_at: datetime
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ReconciliationMatchOut(BaseModel):
    id: uuid.UUID
    match_status: str
    match_basis: str | None
    transaction_record: TransactionRecordOut | None
    external_record: ExternalRecordOut | None
    created_at: datetime


class AuditEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    actor_email: str | None
    payload: dict
    created_at: datetime


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
