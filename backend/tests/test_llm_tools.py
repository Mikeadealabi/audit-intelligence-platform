import uuid
from datetime import date
from decimal import Decimal

from app.models import (
    AppUser,
    ControlDefinition,
    ControlRun,
    ControlVersion,
    DatasetVersion,
    Engagement,
    Finding,
    ImportRun,
    SourceFile,
    Tenant,
    TransactionRecord,
)
from app.services.llm.tools import make_tool_executor


def _setup_dataset(db, tenant_id: uuid.UUID, user_id: uuid.UUID):
    """Creates a tenant-scoped engagement + dataset version with a couple of
    transaction records and a source file, bypassing the API for speed. Returns
    (engagement_id, dataset_version_id, record_ids, source_file_id)."""
    if db.get(Tenant, tenant_id) is None:
        db.add(Tenant(id=tenant_id, name="T"))
        db.flush()  # no relationship() link, so Tenant must be inserted before anything FKs to it
    if db.get(AppUser, user_id) is None:
        db.add(AppUser(id=user_id, email=f"{user_id}@example.com", password_hash="x"))
        db.flush()
    engagement = Engagement(tenant_id=tenant_id, name="E", client_name="C", created_by=user_id)
    db.add(engagement)
    db.flush()

    source_file = SourceFile(
        tenant_id=tenant_id,
        engagement_id=engagement.id,
        uploaded_by=user_id,
        original_filename="f.csv",
        storage_path="x",
        sha256_hash="abc",
        byte_size=10,
        content_type="text/csv",
    )
    db.add(source_file)
    db.flush()
    import_run = ImportRun(
        tenant_id=tenant_id,
        engagement_id=engagement.id,
        source_file_id=source_file.id,
        column_mapping={},
        status="committed",
        created_by=user_id,
    )
    db.add(import_run)
    db.flush()

    dataset_version = DatasetVersion(
        tenant_id=tenant_id,
        engagement_id=engagement.id,
        import_run_id=import_run.id,
        version_number=1,
        source_file_sha256="abc",
        mapping_snapshot={},
        committed_by=user_id,
    )
    db.add(dataset_version)
    db.flush()

    r1 = TransactionRecord(
        tenant_id=tenant_id,
        engagement_id=engagement.id,
        dataset_version_id=dataset_version.id,
        source_row_number=1,
        supplier_name="Acme Ltd",
        invoice_reference="INV-1",
        currency="NGN",
        amount=Decimal("1000.00"),
        transaction_date=date(2026, 1, 1),
        raw_row={},
    )
    r2 = TransactionRecord(
        tenant_id=tenant_id,
        engagement_id=engagement.id,
        dataset_version_id=dataset_version.id,
        source_row_number=2,
        supplier_name="acme ltd",
        invoice_reference="inv-1",
        currency="NGN",
        amount=Decimal("1000.00"),
        transaction_date=date(2026, 1, 2),
        raw_row={},
    )
    db.add_all([r1, r2])
    db.flush()
    db.commit()
    return engagement.id, dataset_version.id, [r1.id, r2.id], source_file.id


def test_get_transaction_records_scoped_to_dataset(db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    engagement_id, dataset_version_id, record_ids, _ = _setup_dataset(db, tenant_id, user_id)

    executor = make_tool_executor(
        db, tenant_id=tenant_id, engagement_id=engagement_id, dataset_version_id=dataset_version_id, max_records=25
    )
    result = executor("get_transaction_records", {"record_ids": [str(r) for r in record_ids]})
    assert len(result.content) == 2
    assert set(result.evidence_ids) == {str(r) for r in record_ids}


def test_get_transaction_records_cannot_see_other_tenants_data(db):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    user_id = uuid.uuid4()
    _, _, record_ids_a, _ = _setup_dataset(db, tenant_a, user_id)
    engagement_b, dataset_b, _, _ = _setup_dataset(db, tenant_b, user_id)

    # Tool executor scoped to tenant B, asked for tenant A's record IDs
    executor = make_tool_executor(
        db, tenant_id=tenant_b, engagement_id=engagement_b, dataset_version_id=dataset_b, max_records=25
    )
    result = executor("get_transaction_records", {"record_ids": [str(r) for r in record_ids_a]})
    assert result.content == []
    assert result.evidence_ids == []


def test_compare_invoice_candidates_finds_case_insensitive_match(db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    engagement_id, dataset_version_id, record_ids, _ = _setup_dataset(db, tenant_id, user_id)

    executor = make_tool_executor(
        db, tenant_id=tenant_id, engagement_id=engagement_id, dataset_version_id=dataset_version_id, max_records=25
    )
    result = executor("compare_invoice_candidates", {"invoice_id": str(record_ids[0]), "candidate_limit": 10})
    assert len(result.content) == 1
    assert result.content[0]["id"] == str(record_ids[1])


def test_check_approval_against_policy_always_unsupported(db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    engagement_id, dataset_version_id, record_ids, _ = _setup_dataset(db, tenant_id, user_id)

    executor = make_tool_executor(
        db, tenant_id=tenant_id, engagement_id=engagement_id, dataset_version_id=dataset_version_id, max_records=25
    )
    result = executor(
        "check_approval_against_policy", {"transaction_id": str(record_ids[0]), "policy_version_id": None}
    )
    assert result.content["supported"] is False
    assert not result.is_error


def test_get_document_metadata_never_includes_storage_path(db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    engagement_id, dataset_version_id, _, source_file_id = _setup_dataset(db, tenant_id, user_id)

    executor = make_tool_executor(
        db, tenant_id=tenant_id, engagement_id=engagement_id, dataset_version_id=dataset_version_id, max_records=25
    )
    result = executor("get_document_metadata", {"document_ids": [str(source_file_id)]})
    assert len(result.content) == 1
    assert "storage_path" not in result.content[0]
    assert result.content[0]["original_filename"] == "f.csv"


def test_invalid_uuid_argument_returns_error_not_crash(db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    engagement_id, dataset_version_id, _, _ = _setup_dataset(db, tenant_id, user_id)

    executor = make_tool_executor(
        db, tenant_id=tenant_id, engagement_id=engagement_id, dataset_version_id=dataset_version_id, max_records=25
    )
    result = executor("get_finding_context", {"finding_id": "not-a-uuid"})
    assert result.is_error is True


def test_unknown_tool_name_returns_error_not_crash(db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    engagement_id, dataset_version_id, _, _ = _setup_dataset(db, tenant_id, user_id)

    executor = make_tool_executor(
        db, tenant_id=tenant_id, engagement_id=engagement_id, dataset_version_id=dataset_version_id, max_records=25
    )
    result = executor("delete_everything", {})
    assert result.is_error is True


def test_get_finding_context_returns_evidence_ids(db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    engagement_id, dataset_version_id, record_ids, _ = _setup_dataset(db, tenant_id, user_id)

    control_definition = ControlDefinition(code="duplicate_invoice_candidates", name="n", description="d")
    db.add(control_definition)
    db.flush()
    control_version = ControlVersion(control_definition_id=control_definition.id, version_number=1, logic_doc_ref="x")
    db.add(control_version)
    db.flush()
    control_run = ControlRun(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        dataset_version_id=dataset_version_id,
        control_version_id=control_version.id,
        run_by=user_id,
        finding_count=1,
    )
    db.add(control_run)
    db.flush()
    finding = Finding(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        control_run_id=control_run.id,
        severity="medium",
        summary="dup",
        evidence_record_ids=[str(r) for r in record_ids],
    )
    db.add(finding)
    db.commit()

    executor = make_tool_executor(
        db, tenant_id=tenant_id, engagement_id=engagement_id, dataset_version_id=dataset_version_id, max_records=25
    )
    result = executor("get_finding_context", {"finding_id": str(finding.id)})
    assert result.content["severity"] == "medium"
    assert set(result.evidence_ids) == {str(r) for r in record_ids}
