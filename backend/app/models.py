import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=_now)


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=_now)


class TenantMembership(Base):
    __tablename__ = "tenant_membership"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "member" | "admin"
    created_at: Mapped[datetime] = mapped_column(default=_now)


class TenantInvite(Base):
    __tablename__ = "tenant_invite"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # "member" | "admin" — the role granted on accept
    # sha256 hex of a secrets.token_urlsafe(32) token — not bcrypt. A 256-bit
    # random token needs an indexable exact-match lookup; bcrypt's slow/salted
    # design is for low-entropy secrets like passwords, not this. See DECISIONS.md.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(default=_now)
    expires_at: Mapped[datetime] = mapped_column()
    accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)


class Engagement(Base):
    __tablename__ = "engagement"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    client_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(default=_now)
    # Set by POST .../purge-data (soft purge: raw file bytes + raw_row redacted,
    # canonical fields/findings/audit trail untouched). Null until first purged.
    data_purged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    data_purged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)


class SourceFile(Base):
    __tablename__ = "source_file"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    original_filename: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str] = mapped_column(String(1000))
    sha256_hash: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column()
    content_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=_now)
    # Set by POST .../purge-data when this file's bytes are deleted from storage.
    # Metadata (filename, hash, size) is kept for provenance even after content_purged_at is set.
    content_purged_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ImportRun(Base):
    __tablename__ = "import_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    source_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_file.id"))
    column_mapping: Mapped[dict] = mapped_column(JSON)
    # Only used by the external-record (reconciliation) import flow — a free-text
    # caller-supplied label, never a real gateway/ERP connector identity. Null for
    # the transaction-record import flow.
    source_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    row_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    validation_errors: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(default=_now)


class DatasetVersion(Base):
    __tablename__ = "dataset_version"
    __table_args__ = (UniqueConstraint("import_run_id", name="uq_dataset_version_import_run"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    import_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_run.id"))
    version_number: Mapped[int] = mapped_column()
    source_file_sha256: Mapped[str] = mapped_column(String(64))
    mapping_snapshot: Mapped[dict] = mapped_column(JSON)
    committed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    committed_at: Mapped[datetime] = mapped_column(default=_now)


class TransactionRecord(Base):
    __tablename__ = "transaction_record"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_version.id"), index=True)
    source_row_number: Mapped[int] = mapped_column()
    supplier_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    invoice_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Optional tax fields — only populated when the source file actually maps a
    # column to them. Never computed or filled in by this platform; see
    # tax_calculation_variance in docs/control-library.md.
    tax_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recorded_vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    recorded_wht_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    raw_row: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class ExternalRecordBatch(Base):
    """The second, independently-sourced side of a reconciliation — e.g. a bank or
    payment-gateway statement, uploaded and versioned the same way transaction_record
    is (immutable, hashed). `source_label` is a free-text caller-supplied label
    ("GTBank NGN statement — Jan 2026"), never a real gateway/ERP connector identity —
    no such connector exists yet, see docs/reconciliation.md."""

    __tablename__ = "external_record_batch"
    __table_args__ = (UniqueConstraint("import_run_id", name="uq_external_record_batch_import_run"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    import_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_run.id"))
    source_label: Mapped[str] = mapped_column(String(200))
    version_number: Mapped[int] = mapped_column()
    source_file_sha256: Mapped[str] = mapped_column(String(64))
    mapping_snapshot: Mapped[dict] = mapped_column(JSON)
    committed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    committed_at: Mapped[datetime] = mapped_column(default=_now)


class ExternalRecord(Base):
    __tablename__ = "external_record"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    external_record_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("external_record_batch.id"), index=True)
    source_row_number: Mapped[int] = mapped_column()
    counterparty_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    raw_row: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class ReconciliationRun(Base):
    """One execution of matching a dataset_version's transaction_records against an
    external_record_batch. `method` and `parameters` exist now so a future
    tolerance-based/fuzzy method can be added without a schema change — only
    "exact_match" has an implementation today; see docs/reconciliation.md."""

    __tablename__ = "reconciliation_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_version.id"))
    external_record_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("external_record_batch.id"))
    method: Mapped[str] = mapped_column(String(50), default="exact_match")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    started_at: Mapped[datetime] = mapped_column(default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    run_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    matched_count: Mapped[int] = mapped_column(default=0)
    unmatched_transaction_count: Mapped[int] = mapped_column(default=0)
    unmatched_external_count: Mapped[int] = mapped_column(default=0)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)


class ReconciliationMatch(Base):
    """One outcome row per transaction_record and/or external_record considered by
    a reconciliation_run: a matched pair (both FKs set), or a one-sided unmatched
    record (exactly one FK set). `match_basis` documents *why* — e.g.
    "exact:amount+currency+reference" or "ambiguous_duplicate_key" — so a reviewer
    never has to guess why something wasn't paired."""

    __tablename__ = "reconciliation_match"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_run.id"), index=True)
    transaction_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transaction_record.id"), nullable=True)
    external_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("external_record.id"), nullable=True)
    match_status: Mapped[str] = mapped_column(String(30))
    match_basis: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class ControlDefinition(Base):
    __tablename__ = "control_definition"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(default=_now)


class ControlVersion(Base):
    __tablename__ = "control_version"
    __table_args__ = (
        UniqueConstraint("control_definition_id", "version_number", name="uq_control_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    control_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("control_definition.id"))
    version_number: Mapped[int] = mapped_column()
    logic_doc_ref: Mapped[str] = mapped_column(String(300))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class ControlRun(Base):
    __tablename__ = "control_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_version.id"))
    control_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("control_version.id"))
    status: Mapped[str] = mapped_column(String(20), default="completed")
    started_at: Mapped[datetime] = mapped_column(default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    run_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    finding_count: Mapped[int] = mapped_column(default=0)
    skipped_row_count: Mapped[int] = mapped_column(default=0)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)


class Finding(Base):
    __tablename__ = "finding"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    control_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("control_run.id"), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="open")
    summary: Mapped[str] = mapped_column(String(2000))
    evidence_record_ids: Mapped[list] = mapped_column(JSON)
    # Layered on top of `status` (the disposition) rather than replacing it — see
    # docs/data-dictionary.md for why disposition stays a single status field for
    # now. "not_required" until a disposition exists; a disposition always resets
    # this to "pending_review" (see record_disposition), so re-disposing after a
    # rejection naturally re-queues it for review.
    sign_off_status: Mapped[str] = mapped_column(String(20), default="not_required")
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    signed_off_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Set by record_disposition — who recorded the current status, so sign-off can
    # enforce a real second person reviewed it. NULL on findings dispositioned
    # before this column existed; the sign-off enforcement check simply skips
    # those (documented transitional gap, see DECISIONS.md).
    disposition_recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class InvestigationRun(Base):
    __tablename__ = "investigation_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finding.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|completed|failed
    model_id: Mapped[str] = mapped_column(String(100))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    requested_at: Mapped[datetime] = mapped_column(default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_call_log: Mapped[list] = mapped_column(JSON, default=list)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class ControlConfiguration(Base):
    """Per-engagement, per-control saved settings: whether this control should
    auto-run every time a dataset version is committed, and (for controls that
    require them) the parameters to run it with. See
    app/services/control_automation.py and docs/control-library.md."""

    __tablename__ = "control_configuration"
    __table_args__ = (
        UniqueConstraint("engagement_id", "control_code", name="uq_control_configuration_engagement_control"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    control_code: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(default=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class EngagementPlan(Base):
    """Scope, materiality threshold, and risk assessment captured before fieldwork
    starts — one row per engagement, mirroring ControlConfiguration's per-engagement
    settings-blob pattern but singular rather than keyed by a code. No enforcement
    reads this yet (e.g. materiality-aware findings) — this is capture only, the
    first step toward that documented deferred idea."""

    __tablename__ = "engagement_plan"
    __table_args__ = (UniqueConstraint("engagement_id", name="uq_engagement_plan_engagement"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    materiality_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    materiality_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    scope_notes: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    risk_assessment: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    risk_rating: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "low" | "medium" | "high"
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("engagement.id"), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)
