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


def _setup_engagement_with_findings(client, headers):
    engagement_id = client.post(
        "/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers
    ).json()["id"]

    data = _csv_bytes(
        [
            "Acme,INV-1,NGN,450000.00,2026-01-01",
            "Acme,INV-1,NGN,450000.00,2026-01-01",
            "Globex,INV-9,NGN,90000.00,2026-01-05",
        ]
    )
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
    return engagement_id, commit["dataset_version_id"]


def test_analytics_aggregates_findings_and_suppliers(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id, dataset_version_id = _setup_engagement_with_findings(client, headers)

    resp = client.get(f"/engagements/{engagement_id}/analytics", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["dataset_version_id"] == dataset_version_id
    assert body["dataset_version_number"] == 1

    assert body["findings_by_severity"]["medium"] == 1
    assert body["findings_by_severity"]["high"] == 0
    assert body["findings_by_status"]["open"] == 1

    assert len(body["findings_by_control"]) == 1
    assert body["findings_by_control"][0]["control_code"] == "duplicate_invoice_candidates"
    assert body["findings_by_control"][0]["finding_count"] == 1

    suppliers = {s["supplier_name"]: s for s in body["supplier_summary"]}
    assert suppliers["Acme"]["transaction_count"] == 2
    assert suppliers["Acme"]["total_amount_by_currency"]["NGN"] == "900000.00"
    assert suppliers["Acme"]["flagged_transaction_count"] == 2

    assert suppliers["Globex"]["transaction_count"] == 1
    assert suppliers["Globex"]["flagged_transaction_count"] == 0


def test_analytics_with_no_data_returns_empty_not_an_error(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = client.post(
        "/engagements", json={"name": "Empty Audit", "client_name": "Nobody Ltd"}, headers=headers
    ).json()["id"]

    resp = client.get(f"/engagements/{engagement_id}/analytics", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["dataset_version_id"] is None
    assert body["supplier_summary"] == []
    assert body["findings_by_severity"] == {"high": 0, "medium": 0, "low": 0}


def test_supplier_risk_scores_reward_distinct_controls_over_repeat_hits(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id, dataset_version_id = _setup_engagement_with_findings(client, headers)

    # Acme's two INV-1 transactions (450000.00 each) are also exact multiples of
    # 450000 — a second, independent control firing on the same supplier.
    client.post(
        f"/engagements/{engagement_id}/control-runs",
        json={
            "dataset_version_id": dataset_version_id,
            "control_code": "round_number_transfers",
            "parameters": {"round_to": "450000.00", "currency": "NGN"},
        },
        headers=headers,
    )

    resp = client.get(f"/engagements/{engagement_id}/analytics", headers=headers)
    assert resp.status_code == 200
    scores = {s["supplier_name"]: s for s in resp.json()["supplier_risk_scores"]}

    # duplicate_invoice_candidates (medium, weight 2) + round_number_transfers
    # (low, weight 1) = 3 — two distinct controls, not 3 separate findings
    # double-counted within the same control.
    assert scores["Acme"]["risk_score"] == 3
    assert sorted(scores["Acme"]["controls_hit"]) == ["duplicate_invoice_candidates", "round_number_transfers"]
    assert scores["Acme"]["total_finding_count"] == 3  # 1 duplicate finding + 2 per-transaction round-number findings
    assert scores["Acme"]["severity_breakdown"] == {"high": 0, "medium": 1, "low": 2}

    # Globex was never flagged by anything — it should not appear at all, not
    # appear with a score of zero.
    assert "Globex" not in scores


def test_cross_tenant_cannot_fetch_analytics(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    engagement_id, _ = _setup_engagement_with_findings(client, headers_a)

    resp = client.get(f"/engagements/{engagement_id}/analytics", headers=headers_b)
    assert resp.status_code == 404
