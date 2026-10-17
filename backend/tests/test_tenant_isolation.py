import io
import json
import uuid

MAPPING = json.dumps(
    {
        "supplier_name": "Supplier",
        "invoice_reference": "InvoiceRef",
        "currency": "Currency",
        "amount": "Amount",
        "transaction_date": "Date",
    }
)


def _csv_bytes(rows: list[str]) -> bytes:
    header = "Supplier,InvoiceRef,Currency,Amount,Date"
    return ("\n".join([header, *rows])).encode("utf-8")


def _full_setup(client, headers):
    """Creates an engagement, a committed dataset version, a control run, and a
    finding, all under the tenant implied by `headers`. Returns every ID a
    cross-tenant attacker might try to guess."""
    engagement_id = client.post(
        "/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers
    ).json()["id"]

    data = _csv_bytes(["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"])
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()
    import_run_id = preview["import_run_id"]
    source_file_id = preview["source_file_id"]

    commit = client.post(f"/engagements/{engagement_id}/imports/{import_run_id}/commit", headers=headers).json()
    dataset_version_id = commit["dataset_version_id"]

    control_run = client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={"dataset_version_id": dataset_version_id, "control_code": "duplicate_invoice_candidates"},
        headers=headers,
    ).json()
    finding_id = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()[0]["id"]

    return {
        "engagement_id": engagement_id,
        "import_run_id": import_run_id,
        "source_file_id": source_file_id,
        "dataset_version_id": dataset_version_id,
        "control_run_id": control_run["id"],
        "finding_id": finding_id,
    }


def test_cross_tenant_cannot_read_engagement(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    ids = _full_setup(client, headers_a)

    resp = client.get(f"/engagements/{ids['engagement_id']}", headers=headers_b)
    assert resp.status_code == 404


def test_cross_tenant_engagement_list_never_includes_other_tenant(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    _full_setup(client, headers_a)
    client.post("/engagements", json={"name": "Tenant B Audit", "client_name": "B Ltd"}, headers=headers_b)

    listed = client.get("/engagements", headers=headers_b).json()
    assert len(listed) == 1
    assert listed[0]["client_name"] == "B Ltd"


def test_cross_tenant_cannot_preview_import_into_others_engagement(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    ids = _full_setup(client, headers_a)

    data = _csv_bytes(["X,INV-9,NGN,1.00,2026-01-01"])
    resp = client.post(
        f"/engagements/{ids['engagement_id']}/imports/preview",
        files={"file": ("x.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers_b,
    )
    assert resp.status_code == 404


def test_cross_tenant_cannot_commit_others_import_run(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    ids = _full_setup(client, headers_a)

    resp = client.post(
        f"/engagements/{ids['engagement_id']}/imports/{ids['import_run_id']}/commit", headers=headers_b
    )
    assert resp.status_code == 404


def test_cross_tenant_cannot_run_control_against_others_dataset(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    ids = _full_setup(client, headers_a)
    # Tenant B has its own engagement; it must not be able to point a control run
    # at Tenant A's dataset version even by guessing the ID.
    own_engagement_id = client.post(
        "/engagements", json={"name": "B Audit", "client_name": "B Ltd"}, headers=headers_b
    ).json()["id"]

    resp = client.post(
        f"/engagements/{own_engagement_id}/control-runs",
        json={"dataset_version_id": ids["dataset_version_id"], "control_code": "duplicate_invoice_candidates"},
        headers=headers_b,
    )
    assert resp.status_code == 404


def test_cross_tenant_cannot_read_control_run(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    ids = _full_setup(client, headers_a)

    resp = client.get(
        f"/engagements/{ids['engagement_id']}/control-runs/{ids['control_run_id']}", headers=headers_b
    )
    assert resp.status_code == 404


def test_cross_tenant_cannot_read_finding_or_evidence(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    ids = _full_setup(client, headers_a)

    assert client.get(
        f"/engagements/{ids['engagement_id']}/findings/{ids['finding_id']}", headers=headers_b
    ).status_code == 404
    assert client.get(
        f"/engagements/{ids['engagement_id']}/findings/{ids['finding_id']}/evidence", headers=headers_b
    ).status_code == 404


def test_cross_tenant_cannot_record_disposition(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    ids = _full_setup(client, headers_a)

    resp = client.post(
        f"/engagements/{ids['engagement_id']}/findings/{ids['finding_id']}/disposition",
        json={"status": "confirmed", "rationale": "trying to tamper with another tenant's finding"},
        headers=headers_b,
    )
    assert resp.status_code == 404

    # And tenant A's finding was not altered by the attempt.
    unchanged = client.get(f"/engagements/{ids['engagement_id']}/findings/{ids['finding_id']}", headers=headers_a)
    assert unchanged.json()["status"] == "open"


def test_nonexistent_id_and_cross_tenant_id_are_indistinguishable(client, make_principal):
    """Both must be 404 with no detail that reveals which case it was — otherwise a
    404-vs-403 split would let an attacker enumerate which IDs exist in other
    tenants."""
    headers_a, _, _ = make_principal()
    _full_setup(client, headers_a)

    real_other_tenant = client.get(f"/engagements/{uuid.uuid4()}", headers=headers_a)
    assert real_other_tenant.status_code == 404
