from app.models import TenantInvite


def test_member_cannot_create_invite(client, make_principal):
    headers, _, _ = make_principal(role="member")
    resp = client.post("/team/invites", json={"email": "new@example.com", "role": "member"}, headers=headers)
    assert resp.status_code == 403


def test_member_cannot_list_or_revoke_invites(client, make_principal):
    admin_headers, _, tenant_id = make_principal(role="admin")
    created = client.post(
        "/team/invites", json={"email": "new@example.com", "role": "member"}, headers=admin_headers
    ).json()

    member_headers, _, _ = make_principal(role="member", tenant_id=tenant_id)
    assert client.get("/team/invites", headers=member_headers).status_code == 403
    assert client.post(f"/team/invites/{created['id']}/revoke", headers=member_headers).status_code == 403


def test_create_invite_rejects_already_registered_email(client, make_principal):
    headers, _, _ = make_principal(role="admin")
    resp = client.post(
        "/auth/signup",
        json={"email": "taken@example.com", "password": "a-long-password", "tenant_name": "Other Firm"},
    )
    assert resp.status_code == 201

    resp = client.post("/team/invites", json={"email": "taken@example.com", "role": "member"}, headers=headers)
    assert resp.status_code == 409


def test_accept_invite_happy_path_creates_working_account(client, make_principal):
    headers, _, tenant_id = make_principal(role="admin")
    invite = client.post(
        "/team/invites", json={"email": "teammate@example.com", "role": "member"}, headers=headers
    ).json()
    assert invite["invite_url"].endswith(f"/accept-invite?token={invite['token']}")

    preview = client.get(f"/invites/{invite['token']}")
    assert preview.status_code == 200
    assert preview.json()["email"] == "teammate@example.com"
    assert preview.json()["role"] == "member"

    accept = client.post(f"/invites/{invite['token']}/accept", json={"password": "a-very-long-password"})
    assert accept.status_code == 200
    token = accept.json()["access_token"]

    members = client.get("/team/members", headers={"Authorization": f"Bearer {token}"})
    assert members.status_code == 200
    assert any(m["email"] == "teammate@example.com" and m["role"] == "member" for m in members.json())


def test_accepting_invite_twice_fails(client, make_principal):
    headers, _, _ = make_principal(role="admin")
    invite = client.post(
        "/team/invites", json={"email": "teammate2@example.com", "role": "member"}, headers=headers
    ).json()
    first = client.post(f"/invites/{invite['token']}/accept", json={"password": "a-very-long-password"})
    assert first.status_code == 200
    second = client.post(f"/invites/{invite['token']}/accept", json={"password": "a-very-long-password"})
    assert second.status_code == 410


def test_revoked_invite_cannot_be_accepted(client, make_principal):
    headers, _, _ = make_principal(role="admin")
    invite = client.post(
        "/team/invites", json={"email": "teammate3@example.com", "role": "member"}, headers=headers
    ).json()
    revoke = client.post(f"/team/invites/{invite['id']}/revoke", headers=headers)
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"

    accept = client.post(f"/invites/{invite['token']}/accept", json={"password": "a-very-long-password"})
    assert accept.status_code == 410


def test_revoking_an_already_accepted_invite_is_rejected(client, make_principal):
    headers, _, _ = make_principal(role="admin")
    invite = client.post(
        "/team/invites", json={"email": "teammate4@example.com", "role": "member"}, headers=headers
    ).json()
    client.post(f"/invites/{invite['token']}/accept", json={"password": "a-very-long-password"})

    resp = client.post(f"/team/invites/{invite['id']}/revoke", headers=headers)
    assert resp.status_code == 409


def test_unknown_token_is_404(client):
    assert client.get("/invites/not-a-real-token").status_code == 404
    assert client.post("/invites/not-a-real-token/accept", json={"password": "a-very-long-password"}).status_code == 404


def test_expired_invite_cannot_be_accepted(client, make_principal, db):
    headers, _, tenant_id = make_principal(role="admin")
    invite_resp = client.post(
        "/team/invites", json={"email": "teammate5@example.com", "role": "member"}, headers=headers
    ).json()

    from datetime import UTC, datetime, timedelta

    invite = db.query(TenantInvite).filter_by(tenant_id=tenant_id).one()
    invite.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()

    accept = client.post(f"/invites/{invite_resp['token']}/accept", json={"password": "a-very-long-password"})
    assert accept.status_code == 410
