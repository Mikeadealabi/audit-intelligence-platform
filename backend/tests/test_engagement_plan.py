def _engagement(client, headers) -> str:
    resp = client.post("/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers)
    return resp.json()["id"]


def test_plan_defaults_to_all_nulls_before_any_put(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)

    resp = client.get(f"/engagements/{engagement_id}/plan", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["materiality_amount"] is None
    assert body["materiality_currency"] is None
    assert body["scope_notes"] is None
    assert body["risk_assessment"] is None
    assert body["risk_rating"] is None
    assert body["updated_at"] is None


def test_put_upserts_plan_and_is_reflected_on_next_get(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)

    put_resp = client.put(
        f"/engagements/{engagement_id}/plan",
        json={
            "materiality_amount": "5000000.00",
            "materiality_currency": "NGN",
            "scope_notes": "FY2026 Q3 branch transactions only.",
            "risk_assessment": "Elevated risk of related-party lending.",
            "risk_rating": "high",
        },
        headers=headers,
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["risk_rating"] == "high"
    assert put_resp.json()["updated_at"] is not None

    get_resp = client.get(f"/engagements/{engagement_id}/plan", headers=headers)
    assert get_resp.json()["materiality_currency"] == "NGN"
    assert get_resp.json()["scope_notes"] == "FY2026 Q3 branch transactions only."

    # A second PUT updates the same row rather than creating another one.
    second_put = client.put(
        f"/engagements/{engagement_id}/plan",
        json={"risk_rating": "low"},
        headers=headers,
    )
    assert second_put.json()["risk_rating"] == "low"
    assert second_put.json()["materiality_currency"] is None  # not re-sent, so cleared — PUT is a full replace


def test_invalid_risk_rating_rejected(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)

    resp = client.put(
        f"/engagements/{engagement_id}/plan",
        json={"risk_rating": "extreme"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_plan_put_is_audited(client, make_principal):
    headers, _, tenant_id = make_principal()
    engagement_id = _engagement(client, headers)

    client.put(
        f"/engagements/{engagement_id}/plan",
        json={"materiality_amount": "100.00", "materiality_currency": "USD"},
        headers=headers,
    )

    events = client.get(f"/engagements/{engagement_id}/activity", headers=headers).json()
    event_types = {e["event_type"] for e in events}
    assert "engagement.plan_updated" in event_types
