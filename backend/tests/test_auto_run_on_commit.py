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


def _commit(client, headers, engagement_id: str, rows: list[str]) -> dict:
    data = _csv_bytes(rows)
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()
    return client.post(
        f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers
    ).json()


def _engagement(client, headers) -> str:
    resp = client.post("/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers)
    return resp.json()["id"]


def _configure(client, headers, engagement_id: str, control_code: str, *, enabled: bool, parameters: dict | None = None):
    resp = client.put(
        f"/engagements/{engagement_id}/control-configurations/{control_code}",
        json={"enabled": enabled, "parameters": parameters or {}},
        headers=headers,
    )
    assert resp.status_code == 200


def test_no_configured_controls_means_no_auto_run_results(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    commit = _commit(client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"])
    assert commit["auto_run_control_results"] == []


def test_enabled_control_auto_runs_and_creates_findings(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    _configure(client, headers, engagement_id, "duplicate_invoice_candidates", enabled=True)

    commit = _commit(
        client,
        headers,
        engagement_id,
        ["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"],
    )

    results = commit["auto_run_control_results"]
    assert len(results) == 1
    assert results[0]["control_code"] == "duplicate_invoice_candidates"
    assert results[0]["status"] == "completed"
    assert results[0]["finding_count"] == 1

    findings = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()
    assert len(findings) == 1

    activity = client.get(f"/engagements/{engagement_id}/activity", headers=headers).json()
    event_types = [e["event_type"] for e in activity]
    assert "control.run_completed" in event_types


def test_disabled_control_does_not_auto_run(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    _configure(client, headers, engagement_id, "duplicate_invoice_candidates", enabled=False)

    commit = _commit(
        client,
        headers,
        engagement_id,
        ["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"],
    )
    assert commit["auto_run_control_results"] == []
    findings = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()
    assert findings == []


def test_misconfigured_control_is_skipped_not_fatal(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    # threshold_splitting_candidates has no safe default — enabling it with no
    # parameters must not break the commit.
    _configure(client, headers, engagement_id, "threshold_splitting_candidates", enabled=True, parameters={})

    commit = _commit(client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"])
    assert commit["dataset_version_id"]  # the commit itself still succeeded

    results = commit["auto_run_control_results"]
    assert len(results) == 1
    assert results[0]["control_code"] == "threshold_splitting_candidates"
    assert results[0]["status"] == "skipped"
    assert results[0]["skip_reason"]

    activity = client.get(f"/engagements/{engagement_id}/activity", headers=headers).json()
    event_types = [e["event_type"] for e in activity]
    assert "control.autorun_skipped" in event_types


def test_new_vendor_control_auto_runs_with_cross_version_history(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    _configure(client, headers, engagement_id, "new_vendor_candidates", enabled=True)

    first = _commit(client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"])
    # First-ever dataset version: the control is a documented no-op.
    assert first["auto_run_control_results"][0]["status"] == "completed"
    assert first["auto_run_control_results"][0]["finding_count"] == 0

    second = _commit(client, headers, engagement_id, ["Globex,INV-2,NGN,2000.00,2026-02-01"])
    # Second commit has real prior history (Acme) — Globex is genuinely new.
    assert second["auto_run_control_results"][0]["status"] == "completed"
    assert second["auto_run_control_results"][0]["finding_count"] == 1
