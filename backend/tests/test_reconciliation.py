import io
import json

TX_MAPPING = json.dumps(
    {
        "supplier_name": "Supplier",
        "invoice_reference": "InvoiceRef",
        "currency": "Currency",
        "amount": "Amount",
        "transaction_date": "Date",
    }
)

EXT_MAPPING = json.dumps(
    {
        "reference": "Ref",
        "currency": "Currency",
        "amount": "Amount",
        "transaction_date": "Date",
        "counterparty_name": "Counterparty",
    }
)


def _engagement(client, headers) -> str:
    resp = client.post("/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers)
    return resp.json()["id"]


def _committed_dataset_version(client, headers, engagement_id: str, rows: list[str]) -> str:
    header = "Supplier,InvoiceRef,Currency,Amount,Date"
    data = ("\n".join([header, *rows])).encode("utf-8")
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": TX_MAPPING},
        headers=headers,
    ).json()
    commit = client.post(
        f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers
    ).json()
    return commit["dataset_version_id"]


def _committed_external_batch(client, headers, engagement_id: str, rows: list[str], source_label: str = "Bank statement") -> str:
    header = "Ref,Currency,Amount,Date,Counterparty"
    data = ("\n".join([header, *rows])).encode("utf-8")
    preview = client.post(
        f"/engagements/{engagement_id}/external-imports/preview",
        files={"file": ("statement.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": EXT_MAPPING, "source_label": source_label},
        headers=headers,
    ).json()
    commit = client.post(
        f"/engagements/{engagement_id}/external-imports/{preview['import_run_id']}/commit", headers=headers
    ).json()
    return commit["external_record_batch_id"]


def test_exact_match_pairs_up(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"]
    )
    batch_id = _committed_external_batch(
        client, headers, engagement_id, ["INV-1,NGN,1000.00,2026-01-02,Acme Ltd"]
    )

    run_resp = client.post(
        f"/engagements/{engagement_id}/reconciliation-runs",
        json={"dataset_version_id": dataset_version_id, "external_record_batch_id": batch_id},
        headers=headers,
    )
    assert run_resp.status_code == 201
    body = run_resp.json()
    assert body["matched_count"] == 1
    assert body["unmatched_transaction_count"] == 0
    assert body["unmatched_external_count"] == 0
    assert body["method"] == "exact_match"

    matches = client.get(
        f"/engagements/{engagement_id}/reconciliation-runs/{body['id']}/matches", headers=headers
    ).json()
    assert len(matches) == 1
    assert matches[0]["match_status"] == "matched"
    assert matches[0]["match_basis"] == "exact:amount+currency+reference"
    assert matches[0]["transaction_record"]["invoice_reference"] == "INV-1"
    assert matches[0]["external_record"]["reference"] == "INV-1"


def test_unmatched_on_each_side(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client, headers, engagement_id, ["Acme,INV-2,NGN,500.00,2026-01-01"]
    )
    batch_id = _committed_external_batch(
        client, headers, engagement_id, ["EXT-9,NGN,300.00,2026-01-03,Unknown Payee"]
    )

    run_resp = client.post(
        f"/engagements/{engagement_id}/reconciliation-runs",
        json={"dataset_version_id": dataset_version_id, "external_record_batch_id": batch_id},
        headers=headers,
    )
    body = run_resp.json()
    assert body["matched_count"] == 0
    assert body["unmatched_transaction_count"] == 1
    assert body["unmatched_external_count"] == 1

    tx_unmatched = client.get(
        f"/engagements/{engagement_id}/reconciliation-runs/{body['id']}/matches",
        params={"match_status": "unmatched_transaction"},
        headers=headers,
    ).json()
    assert len(tx_unmatched) == 1
    assert tx_unmatched[0]["match_basis"] == "no_matching_external_record"
    assert tx_unmatched[0]["external_record"] is None

    ext_unmatched = client.get(
        f"/engagements/{engagement_id}/reconciliation-runs/{body['id']}/matches",
        params={"match_status": "unmatched_external"},
        headers=headers,
    ).json()
    assert len(ext_unmatched) == 1
    assert ext_unmatched[0]["match_basis"] == "no_matching_transaction_record"
    assert ext_unmatched[0]["transaction_record"] is None


def test_ambiguous_duplicate_key_is_not_guessed(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client,
        headers,
        engagement_id,
        ["Acme,INV-DUP,NGN,100.00,2026-01-01", "Acme,INV-DUP,NGN,100.00,2026-01-05"],
    )
    batch_id = _committed_external_batch(
        client, headers, engagement_id, ["INV-DUP,NGN,100.00,2026-01-02,Acme Ltd"]
    )

    run_resp = client.post(
        f"/engagements/{engagement_id}/reconciliation-runs",
        json={"dataset_version_id": dataset_version_id, "external_record_batch_id": batch_id},
        headers=headers,
    )
    body = run_resp.json()
    assert body["matched_count"] == 0
    assert body["unmatched_transaction_count"] == 2
    assert body["unmatched_external_count"] == 1

    matches = client.get(
        f"/engagements/{engagement_id}/reconciliation-runs/{body['id']}/matches", headers=headers
    ).json()
    assert all(m["match_basis"] == "ambiguous_duplicate_key" for m in matches)


def test_unsupported_method_rejected(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"]
    )
    batch_id = _committed_external_batch(client, headers, engagement_id, ["INV-1,NGN,1000.00,2026-01-02,Acme Ltd"])

    resp = client.post(
        f"/engagements/{engagement_id}/reconciliation-runs",
        json={
            "dataset_version_id": dataset_version_id,
            "external_record_batch_id": batch_id,
            "method": "fuzzy_tolerance",
        },
        headers=headers,
    )
    assert resp.status_code == 400


def test_dataset_version_and_batch_must_belong_to_engagement(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    other_engagement_id = _engagement(client, headers)
    dataset_version_id = _committed_dataset_version(
        client, headers, engagement_id, ["Acme,INV-1,NGN,1000.00,2026-01-01"]
    )
    batch_id = _committed_external_batch(client, headers, engagement_id, ["INV-1,NGN,1000.00,2026-01-02,Acme Ltd"])

    resp = client.post(
        f"/engagements/{other_engagement_id}/reconciliation-runs",
        json={"dataset_version_id": dataset_version_id, "external_record_batch_id": batch_id},
        headers=headers,
    )
    assert resp.status_code == 404


def test_external_batches_are_listed(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)
    _committed_external_batch(
        client, headers, engagement_id, ["INV-1,NGN,1000.00,2026-01-02,Acme Ltd"], source_label="Zenith statement"
    )

    batches = client.get(f"/engagements/{engagement_id}/external-imports/batches", headers=headers).json()
    assert len(batches) == 1
    assert batches[0]["source_label"] == "Zenith statement"
    assert batches[0]["version_number"] == 1
