MAPPING = {
    "supplier_name": "Supplier",
    "invoice_reference": "InvoiceRef",
    "currency": "Currency",
    "amount": "Amount",
    "transaction_date": "Date",
}


def _engagement(client, headers) -> str:
    resp = client.post("/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers)
    return resp.json()["id"]


def _finding_with_disposition(client, headers, status_value: str = "confirmed") -> tuple[str, str]:
    import io
    import json

    engagement_id = _engagement(client, headers)
    header = "Supplier,InvoiceRef,Currency,Amount,Date"
    rows = ["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"]
    data = ("\n".join([header, *rows])).encode("utf-8")

    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": json.dumps(MAPPING)},
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
        json={"status": status_value, "rationale": "Reviewed against client-supplied invoice log."},
        headers=headers,
    )
    return engagement_id, finding_id


def test_disposition_queues_finding_for_review(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id, finding_id = _finding_with_disposition(client, headers)

    finding = client.get(f"/engagements/{engagement_id}/findings/{finding_id}", headers=headers).json()
    assert finding["sign_off_status"] == "pending_review"


def test_sign_off_approve_happy_path(client, make_principal):
    preparer_headers, _, tenant_id = make_principal(role="admin")
    engagement_id, finding_id = _finding_with_disposition(client, preparer_headers)
    reviewer_headers, _, _ = make_principal(role="admin", tenant_id=tenant_id)

    resp = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/sign-off",
        json={"decision": "approve", "comment": "Agreed with the preparer's disposition."},
        headers=reviewer_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sign_off_status"] == "signed_off"
    assert body["signed_off_by"] is not None
    assert body["signed_off_at"] is not None

    events = client.get(f"/engagements/{engagement_id}/activity", headers=preparer_headers).json()
    assert "finding.signed_off" in {e["event_type"] for e in events}


def test_sign_off_reject_keeps_disposition_but_flips_sign_off_status(client, make_principal):
    preparer_headers, _, tenant_id = make_principal(role="admin")
    engagement_id, finding_id = _finding_with_disposition(client, preparer_headers)
    reviewer_headers, _, _ = make_principal(role="admin", tenant_id=tenant_id)

    resp = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/sign-off",
        json={"decision": "reject", "comment": "Needs more support before I'll sign off."},
        headers=reviewer_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sign_off_status"] == "rejected"
    assert body["status"] == "confirmed"  # disposition itself is untouched by a rejection

    # Re-disposing naturally re-queues it for review.
    redispose = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/disposition",
        json={"status": "false_positive", "rationale": "Follow-up with client resolved this."},
        headers=preparer_headers,
    )
    assert redispose.json()["sign_off_status"] == "pending_review"


def test_preparer_cannot_sign_off_their_own_disposition(client, make_principal):
    preparer_headers, _, _ = make_principal(role="admin")
    engagement_id, finding_id = _finding_with_disposition(client, preparer_headers)

    resp = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/sign-off",
        json={"decision": "approve", "comment": "Signing off my own work."},
        headers=preparer_headers,
    )
    assert resp.status_code == 409
    assert "yourself" in resp.json()["detail"]


def test_disposition_records_who_prepared_it(client, make_principal):
    headers, user_id, _ = make_principal(role="admin")
    engagement_id, finding_id = _finding_with_disposition(client, headers)

    finding = client.get(f"/engagements/{engagement_id}/findings/{finding_id}", headers=headers).json()
    assert finding["disposition_recorded_by"] == str(user_id)


def test_cannot_sign_off_an_open_finding(client, make_principal):
    import io
    import json

    headers, _, _ = make_principal(role="admin")
    engagement_id = _engagement(client, headers)
    header = "Supplier,InvoiceRef,Currency,Amount,Date"
    data = ("\n".join([header, "Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"])).encode()
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": json.dumps(MAPPING)},
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

    resp = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/sign-off",
        json={"decision": "approve", "comment": "n/a"},
        headers=headers,
    )
    assert resp.status_code == 409


def test_cannot_double_sign_off(client, make_principal):
    preparer_headers, _, tenant_id = make_principal(role="admin")
    engagement_id, finding_id = _finding_with_disposition(client, preparer_headers)
    reviewer_headers, _, _ = make_principal(role="admin", tenant_id=tenant_id)

    first = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/sign-off",
        json={"decision": "approve", "comment": "Looks right."},
        headers=reviewer_headers,
    )
    assert first.status_code == 200

    second = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/sign-off",
        json={"decision": "approve", "comment": "Again?"},
        headers=reviewer_headers,
    )
    assert second.status_code == 409


def test_member_role_cannot_sign_off(client, make_principal):
    admin_headers, _, tenant_id = make_principal(role="admin")
    engagement_id, finding_id = _finding_with_disposition(client, admin_headers)

    member_headers, _, _ = make_principal(role="member", tenant_id=tenant_id)
    resp = client.post(
        f"/engagements/{engagement_id}/findings/{finding_id}/sign-off",
        json={"decision": "approve", "comment": "Trying as a non-admin."},
        headers=member_headers,
    )
    assert resp.status_code == 403
