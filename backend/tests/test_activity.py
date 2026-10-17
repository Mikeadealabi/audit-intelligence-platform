import io
import json

from app.models import AppUser

MAPPING = json.dumps(
    {
        "supplier_name": "Supplier",
        "invoice_reference": "InvoiceRef",
        "currency": "Currency",
        "amount": "Amount",
        "transaction_date": "Date",
    }
)


def test_activity_lists_events_newest_first_with_actor_email(client, make_principal, db):
    headers, user_id, _ = make_principal()
    email = db.get(AppUser, user_id).email
    engagement_id = client.post(
        "/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers
    ).json()["id"]

    data = (b"Supplier,InvoiceRef,Currency,Amount,Date\nAcme,INV-1,NGN,1000.00,2026-01-01")
    preview = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        files={"file": ("txns.csv", io.BytesIO(data), "text/csv")},
        data={"column_mapping": MAPPING},
        headers=headers,
    ).json()
    client.post(f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit", headers=headers)

    resp = client.get(f"/engagements/{engagement_id}/activity", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    event_types = [e["event_type"] for e in body]
    assert event_types[0] == "import.committed"
    assert "import.preview_created" in event_types
    assert "engagement.created" in event_types
    for e in body:
        assert e["actor_email"] == email

    # Newest first.
    created_ats = [e["created_at"] for e in body]
    assert created_ats == sorted(created_ats, reverse=True)


def test_activity_payload_never_contains_forbidden_keys(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = client.post(
        "/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers
    ).json()["id"]

    resp = client.get(f"/engagements/{engagement_id}/activity", headers=headers)
    body = resp.json()
    for event in body:
        assert "password" not in event["payload"]
        assert "token" not in event["payload"]
        assert "raw_row" not in event["payload"]


def test_activity_respects_limit(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = client.post(
        "/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers
    ).json()["id"]

    resp = client.get(f"/engagements/{engagement_id}/activity?limit=1", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_cross_tenant_cannot_fetch_activity(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    engagement_id = client.post(
        "/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers_a
    ).json()["id"]

    resp = client.get(f"/engagements/{engagement_id}/activity", headers=headers_b)
    assert resp.status_code == 404
