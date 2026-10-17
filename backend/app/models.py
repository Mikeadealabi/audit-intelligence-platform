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


class Engagement(Base):
    __tablename__ = "engagement"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    client_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(default=_now)


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


class ImportRun(Base):
    __tablename__ = "import_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagement.id"), index=True)
    source_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_file.id"))
    column_mapping: Mapped[dict] = mapped_column(JSON)
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
    raw_row: Mapped[dict] = mapped_column(JSON)
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


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("engagement.id"), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)
