def _engagement(client, headers) -> str:
    resp = client.post("/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers)
    return resp.json()["id"]


def test_list_returns_every_registry_control_with_defaults(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)

    resp = client.get(f"/engagements/{engagement_id}/control-configurations", headers=headers)
    assert resp.status_code == 200
    codes = {c["control_code"] for c in resp.json()}
    assert codes == {
        "duplicate_invoice_candidates",
        "threshold_splitting_candidates",
        "new_vendor_candidates",
        "round_number_transfers",
        "tax_calculation_variance",
        "benford_digit_analysis",
    }
    for cfg in resp.json():
        assert cfg["enabled"] is False
        assert cfg["parameters"] == {}
        assert cfg["updated_at"] is None


def test_put_enables_and_persists_parameters(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)

    params = {"threshold_amount": "500000.00", "currency": "NGN", "window_days": 3}
    resp = client.put(
        f"/engagements/{engagement_id}/control-configurations/threshold_splitting_candidates",
        json={"enabled": True, "parameters": params},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["parameters"] == params
    assert body["updated_at"] is not None

    listed = client.get(f"/engagements/{engagement_id}/control-configurations", headers=headers).json()
    saved = next(c for c in listed if c["control_code"] == "threshold_splitting_candidates")
    assert saved["enabled"] is True
    assert saved["parameters"] == params


def test_put_unknown_control_code_rejected(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)

    resp = client.put(
        f"/engagements/{engagement_id}/control-configurations/not_a_real_control",
        json={"enabled": True, "parameters": {}},
        headers=headers,
    )
    assert resp.status_code == 400


def test_put_twice_updates_same_row_not_a_duplicate(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id = _engagement(client, headers)

    client.put(
        f"/engagements/{engagement_id}/control-configurations/duplicate_invoice_candidates",
        json={"enabled": True, "parameters": {}},
        headers=headers,
    )
    client.put(
        f"/engagements/{engagement_id}/control-configurations/duplicate_invoice_candidates",
        json={"enabled": False, "parameters": {}},
        headers=headers,
    )

    listed = client.get(f"/engagements/{engagement_id}/control-configurations", headers=headers).json()
    matching = [c for c in listed if c["control_code"] == "duplicate_invoice_candidates"]
    assert len(matching) == 1
    assert matching[0]["enabled"] is False
