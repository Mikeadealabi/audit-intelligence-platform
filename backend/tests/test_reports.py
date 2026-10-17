import io
import json

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


def test_report_includes_dataset_version_control_run_finding_and_disposition(client, make_principal):
    headers, _, _ = make_principal()
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
    commit = client.post(
        f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers
    ).json()
    client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={"dataset_version_id": commit["dataset_version_id"], "control_code": "duplicate_invoice_candidates"},
        headers=headers,
    )
    finding_id = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()[0]["id"]
    client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/disposition",
        json={"status": "false_positive", "rationale": "Corrected re-issue, confirmed with client"},
        headers=headers,
    )

    report = client.get(f"/engagements/{engagement_id}/reports", headers=headers)
    assert report.status_code == 200
    body = report.json()

    assert body["engagement_name"] == "FY2026 Audit"
    assert len(body["dataset_versions"]) == 1
    assert body["dataset_versions"][0]["version_number"] == 1

    assert len(body["control_runs"]) == 1
    assert body["control_runs"][0]["control_code"] == "duplicate_invoice_candidates"

    assert len(body["findings"]) == 1
    finding = body["findings"][0]
    assert finding["control_code"] == "duplicate_invoice_candidates"
    assert finding["dataset_version_number"] == 1
    assert finding["disposition"]["status"] == "false_positive"
    assert "Corrected re-issue" in finding["disposition"]["rationale"]
    assert finding["latest_investigation"] is None

    assert len(body["limitations"]) >= 3
    assert any("not an audit opinion" in limitation for limitation in body["limitations"])


def test_report_with_no_findings_has_empty_lists_not_an_error(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = client.post(
        "/engagements", json={"name": "Empty Audit", "client_name": "Nobody Ltd"}, headers=headers
    ).json()["id"]

    report = client.get(f"/engagements/{engagement_id}/reports", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert body["dataset_versions"] == []
    assert body["control_runs"] == []
    assert body["findings"] == []
    assert len(body["limitations"]) >= 3


def test_cross_tenant_cannot_fetch_report(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    engagement_id = client.post(
        "/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers_a
    ).json()["id"]

    resp = client.get(f"/engagements/{engagement_id}/reports", headers=headers_b)
    assert resp.status_code == 404
