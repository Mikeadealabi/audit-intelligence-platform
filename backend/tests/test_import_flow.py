import io
import json
import uuid

from app.models import TransactionRecord

MAPPING = json.dumps(
    {
        "supplier_name": "Supplier",
        "invoice_reference": "InvoiceRef",
        "currency": "Currency",
        "amount": "Amount",
        "transaction_date": "Date",
    }
)


def _create_engagement(client, headers) -> str:
    resp = client.post("/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _csv_bytes(rows: list[str]) -> bytes:
    header = "Supplier,InvoiceRef,Currency,Amount,Date"
    return ("\n".join([header, *rows])).encode("utf-8")


def test_preview_returns_counts_and_sample(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _create_engagement(client, headers)

    data = _csv_bytes(["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"])
    resp = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total_rows"] == 2
    assert body["error_row_count"] == 0
    assert len(body["sample_rows"]) == 2


def test_commit_creates_dataset_version_with_only_valid_rows(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _create_engagement(client, headers)

    data = _csv_bytes(
        [
            "Acme,INV-1,NGN,1000.00,2026-01-01",
            "Acme,INV-2,NGN,not-a-number,2026-01-01",  # invalid, must be excluded
        ]
    )
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()
    assert preview["error_row_count"] == 1

    commit = client.post(
        f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit",
        headers=headers,
    )
    assert commit.status_code == 200
    body = commit.json()
    assert body["version_number"] == 1
    assert body["row_count"] == 1  # only the valid row


def test_committed_raw_row_is_stored_encrypted(client, make_principal, db):
    headers, _, _ = make_principal()
    engagement_id = _create_engagement(client, headers)

    data = _csv_bytes(["Acme,INV-1,NGN,1000.00,2026-01-01"])
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()
    commit = client.post(
        f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers
    )
    assert commit.status_code == 200

    record = db.query(TransactionRecord).filter_by(engagement_id=uuid.UUID(engagement_id)).one()
    assert set(record.raw_row.keys()) == {"_encrypted"}
    assert "Acme" not in str(record.raw_row)
    # Canonical typed fields are unaffected by raw_row encryption.
    assert record.supplier_name == "Acme"


def test_commit_twice_returns_conflict(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _create_engagement(client, headers)

    data = _csv_bytes(["Acme,INV-1,NGN,1000.00,2026-01-01"])
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()

    first = client.post(f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers)
    assert first.status_code == 200
    second = client.post(f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers)
    assert second.status_code == 409


def test_commit_unknown_import_run_404(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _create_engagement(client, headers)
    resp = client.post(f"/engagements/{engagement_id}/imports/{uuid.uuid4()}/commit", headers=headers)
    assert resp.status_code == 404


def test_second_commit_in_same_engagement_increments_version(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _create_engagement(client, headers)
    data = _csv_bytes(["Acme,INV-1,NGN,1000.00,2026-01-01"])

    for expected_version in (1, 2):
        preview = client.post(
            f"/engagements/{engagement_id}/imports/preview",
            files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
            data={"column_mapping": MAPPING},
            headers=headers,
        ).json()
        commit = client.post(
            f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers
        ).json()
        assert commit["version_number"] == expected_version
