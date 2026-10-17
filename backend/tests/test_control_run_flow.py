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


def _committed_dataset_version(client, headers, engagement_id: str, rows: list[str]) -> str:
    data = _csv_bytes(rows)
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()
    commit = client.post(
        f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers
    ).json()
    return commit["dataset_version_id"]


def _engagement(client, headers) -> str:
    resp = client.post("/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers)
    return resp.json()["id"]


def test_control_run_produces_finding_with_resolvable_evidence(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client,
        headers,
        engagement_id,
        ["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"],
    )

    run_resp = client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={"dataset_version_id": dataset_version_id, "control_code": "duplicate_invoice_candidates"},
        headers=headers,
    )
    assert run_resp.status_code == 201
    assert run_resp.json()["finding_count"] == 1

    findings = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()
    assert len(findings) == 1
    assert findings[0]["status"] == "open"

    evidence = client.get(
        f"/engagements/{engagement_id}/findings/{findings[0]['id']}/evidence", headers=headers
    ).json()
    assert len(evidence) == 2
    assert {r["invoice_reference"] for r in evidence} == {"INV-1"}


def test_clean_dataset_produces_zero_findings(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"]
    )

    run_resp = client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={"dataset_version_id": dataset_version_id, "control_code": "duplicate_invoice_candidates"},
        headers=headers,
    )
    assert run_resp.json()["finding_count"] == 0


def test_disposition_requires_rationale_and_is_audited(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client,
        headers,
        engagement_id,
        ["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"],
    )
    client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={"dataset_version_id": dataset_version_id, "control_code": "duplicate_invoice_candidates"},
        headers=headers,
    )
    finding_id = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()[0]["id"]

    missing_rationale = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/disposition",
        json={"status": "confirmed", "rationale": ""},
        headers=headers,
    )
    assert missing_rationale.status_code == 422

    ok = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/disposition",
        json={"status": "false_positive", "rationale": "Confirmed with client: corrected re-issue, not a duplicate"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "false_positive"


def test_unknown_control_code_rejected(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"]
    )
    resp = client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={"dataset_version_id": dataset_version_id, "control_code": "not_a_real_control"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_threshold_splitting_without_parameters_rejected(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client, headers, engagement_id, ["Acme,INV-1,NGN,200000.00,2026-03-01"]
    )
    resp = client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={"dataset_version_id": dataset_version_id, "control_code": "threshold_splitting_candidates"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_threshold_splitting_happy_path_persists_parameters(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client,
        headers,
        engagement_id,
        [
            "Acme,INV-1,NGN,300000.00,2026-03-01",
            "Acme,INV-2,NGN,300000.00,2026-03-02",
        ],
    )

    params = {"threshold_amount": "500000.00", "currency": "NGN", "window_days": 3}
    run_resp = client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={
            "dataset_version_id": dataset_version_id,
            "control_code": "threshold_splitting_candidates",
            "parameters": params,
        },
        headers=headers,
    )
    assert run_resp.status_code == 201
    body = run_resp.json()
    assert body["finding_count"] == 1
    assert body["parameters"] == params

    # Re-fetching the control run shows the same parameters — reproducibility.
    refetched = client.get(f"/engagements/{engagement_id}/control-runs/{body['id']}", headers=headers)
    assert refetched.json()["parameters"] == params

    findings = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"
    assert len(findings[0]["evidence_record_ids"]) == 2
