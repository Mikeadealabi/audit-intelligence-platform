import io
import json
import uuid

import pytest

from app.config import settings
from app.models import AuditEvent, ExternalRecord, SourceFile, TransactionRecord
from app.services.dataset_versioning import source_file_storage_key
from app.storage.local import LocalFilesystemStorage

MAPPING = json.dumps(
    {
        "supplier_name": "Supplier",
        "invoice_reference": "InvoiceRef",
        "currency": "Currency",
        "amount": "Amount",
        "transaction_date": "Date",
    }
)


def _engagement(client, headers, name: str = "FY2026 Audit") -> str:
    resp = client.post("/engagements", json={"name": name, "client_name": "Acme Ltd"}, headers=headers)
    return resp.json()["id"]


def _commit_one_file(client, headers, engagement_id: str, rows: list[str]) -> dict:
    header = "Supplier,InvoiceRef,Currency,Amount,Date"
    data = ("\n".join([header, *rows])).encode("utf-8")
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()
    return client.post(f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers).json()


def _disposition_and_sign_off(client, headers, engagement_id: str, make_principal, tenant_id) -> str:
    client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={
            "dataset_version_id": _commit_one_file(
                client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"]
            )["dataset_version_id"],
            "control_code": "duplicate_invoice_candidates",
        },
        headers=headers,
    )
    finding_id = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()[0]["id"]
    client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/disposition",
        json={"status": "confirmed", "rationale": "Reviewed."},
        headers=headers,
    )
    reviewer_headers, _, _ = make_principal(role="admin", tenant_id=tenant_id)
    client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/sign-off",
        json={"decision": "approve", "comment": "Agreed."},
        headers=reviewer_headers,
    )
    return finding_id


def test_member_cannot_purge(client, make_principal):
    headers, _, tenant_id = make_principal(role="member")
    engagement_id = _engagement(client, headers)
    resp = client.post(
        f"/engagements/{engagement_id}/purge-data",
        json={"confirm_engagement_name": "FY2026 Audit"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_wrong_confirmation_name_rejected(client, make_principal):
    headers, _, _ = make_principal(role="admin")
    engagement_id = _engagement(client, headers)
    resp = client.post(
        f"/engagements/{engagement_id}/purge-data",
        json={"confirm_engagement_name": "Wrong Name"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_purge_deletes_file_bytes_and_redacts_raw_row_but_keeps_canonical_data(client, make_principal, db):
    headers, _, tenant_id = make_principal(role="admin")
    engagement_id = _engagement(client, headers)
    finding_id = _disposition_and_sign_off(client, headers, engagement_id, make_principal, tenant_id)

    source_file = db.query(SourceFile).filter_by(tenant_id=tenant_id).one()
    storage = LocalFilesystemStorage(settings.local_storage_dir)
    key = source_file_storage_key(tenant_id, uuid.UUID(engagement_id), source_file.id, source_file.original_filename)
    storage.read(key)  # file exists before purge

    resp = client.post(
        f"/engagements/{engagement_id}/purge-data",
        json={"confirm_engagement_name": "FY2026 Audit"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["already_purged"] is False
    assert body["source_file_count"] == 1
    assert body["transaction_record_count"] == 2

    with pytest.raises(FileNotFoundError):
        storage.read(key)

    db.expire_all()
    record = db.query(TransactionRecord).filter_by(tenant_id=tenant_id).first()
    assert record.raw_row == {"_purged": True}
    assert record.supplier_name == "Acme"  # canonical field untouched
    assert record.amount == 1000

    # Finding, disposition, and sign-off all untouched by the purge.
    finding = client.get(f"/engagements/{engagement_id}/findings/{finding_id}", headers=headers).json()
    assert finding["status"] == "confirmed"
    assert finding["sign_off_status"] == "signed_off"

    engagement = client.get(f"/engagements/{engagement_id}", headers=headers).json()
    assert engagement["data_purged_at"] is not None

    events = [e.event_type for e in db.query(AuditEvent).filter_by(tenant_id=tenant_id).all()]
    assert "engagement.data_purged" in events


def test_repeat_purge_only_purges_newly_added_data(client, make_principal, db):
    headers, _, tenant_id = make_principal(role="admin")
    engagement_id = _engagement(client, headers)
    _commit_one_file(client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"])

    first = client.post(
        f"/engagements/{engagement_id}/purge-data",
        json={"confirm_engagement_name": "FY2026 Audit"},
        headers=headers,
    ).json()
    assert first["already_purged"] is False
    assert first["source_file_count"] == 1

    # A no-op repeat call must succeed (200), not 409 — nothing new to purge yet.
    repeat = client.post(
        f"/engagements/{engagement_id}/purge-data",
        json={"confirm_engagement_name": "FY2026 Audit"},
        headers=headers,
    )
    assert repeat.status_code == 200
    assert repeat.json()["already_purged"] is True
    assert repeat.json()["source_file_count"] == 0

    # New data uploaded after the first purge must still be purgeable.
    _commit_one_file(client, headers, engagement_id, ["Globex,INV-2,NGN,2000.00,2026-01-02"])
    third = client.post(
        f"/engagements/{engagement_id}/purge-data",
        json={"confirm_engagement_name": "FY2026 Audit"},
        headers=headers,
    ).json()
    assert third["already_purged"] is True
    assert third["source_file_count"] == 1  # only the newly uploaded file


def test_commit_after_purge_of_a_still_previewed_import_returns_409(client, make_principal):
    headers, _, tenant_id = make_principal(role="admin")
    engagement_id = _engagement(client, headers)

    header = "Supplier,InvoiceRef,Currency,Amount,Date"
    data = ("\n".join([header, "Acme,INV-1,NGN,1000.00,2026-01-01"])).encode("utf-8")
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()
    # Never committed — left in status="previewed" when the purge runs below.

    client.post(
        f"/engagements/{engagement_id}/purge-data",
        json={"confirm_engagement_name": "FY2026 Audit"},
        headers=headers,
    )

    commit = client.post(f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers)
    assert commit.status_code == 409


def test_external_record_raw_row_is_also_purged(client, make_principal, db):
    headers, _, tenant_id = make_principal(role="admin")
    engagement_id = _engagement(client, headers)

    header = "Counterparty,Reference,Currency,Amount,Date"
    data = ("\n".join([header, "Acme,INV-1,NGN,1000.00,2026-01-01"])).encode("utf-8")
    ext_mapping = json.dumps(
        {
            "counterparty_name": "Counterparty",
            "reference": "Reference",
            "currency": "Currency",
            "amount": "Amount",
            "transaction_date": "Date",
        }
    )
    preview = client.post(
        f"/engagements/{engagement_id}/external-imports/preview",
        files={"file": ("statement.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": ext_mapping, "source_label": "Test bank statement"},
        headers=headers,
    ).json()
    client.post(f"/engagements/{engagement_id}/external-imports/{preview['import_run_id']}/commit", headers=headers)

    client.post(
        f"/engagements/{engagement_id}/purge-data",
        json={"confirm_engagement_name": "FY2026 Audit"},
        headers=headers,
    )

    db.expire_all()
    record = db.query(ExternalRecord).filter_by(tenant_id=tenant_id).one()
    assert record.raw_row == {"_purged": True}
    assert record.reference == "INV-1"  # canonical field untouched
