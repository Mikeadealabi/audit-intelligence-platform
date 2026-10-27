def test_member_can_list_team(client, make_principal):
    admin_headers, _, tenant_id = make_principal(role="admin")
    member_headers, _, _ = make_principal(role="member", tenant_id=tenant_id)

    resp = client.get("/team/members", headers=member_headers)
    assert resp.status_code == 200
    roles = {m["role"] for m in resp.json()}
    assert roles == {"admin", "member"}


def test_member_cannot_revoke_a_member(client, make_principal):
    admin_headers, _, tenant_id = make_principal(role="admin")
    member_headers, member_user_id, _ = make_principal(role="member", tenant_id=tenant_id)

    member_row = next(
        m for m in client.get("/team/members", headers=admin_headers).json() if m["user_id"] == str(member_user_id)
    )
    resp = client.post(f"/team/members/{member_row['id']}/revoke", headers=member_headers)
    assert resp.status_code == 403


def test_cannot_revoke_the_only_admin(client, make_principal):
    admin_headers, admin_user_id, tenant_id = make_principal(role="admin")

    admin_row = next(
        m for m in client.get("/team/members", headers=admin_headers).json() if m["user_id"] == str(admin_user_id)
    )
    resp = client.post(f"/team/members/{admin_row['id']}/revoke", headers=admin_headers)
    assert resp.status_code == 409


def test_can_revoke_an_admin_if_another_admin_remains(client, make_principal):
    admin_headers, admin_user_id, tenant_id = make_principal(role="admin")
    other_admin_headers, _, _ = make_principal(role="admin", tenant_id=tenant_id)

    admin_row = next(
        m for m in client.get("/team/members", headers=other_admin_headers).json() if m["user_id"] == str(admin_user_id)
    )
    resp = client.post(f"/team/members/{admin_row['id']}/revoke", headers=other_admin_headers)
    assert resp.status_code == 204


def test_revoking_a_member_immediately_blocks_their_next_request(client, make_principal):
    admin_headers, _, tenant_id = make_principal(role="admin")
    member_headers, member_user_id, _ = make_principal(role="member", tenant_id=tenant_id)

    member_row = next(
        m for m in client.get("/team/members", headers=admin_headers).json() if m["user_id"] == str(member_user_id)
    )
    resp = client.post(f"/team/members/{member_row['id']}/revoke", headers=admin_headers)
    assert resp.status_code == 204

    # Same JWT, but the underlying membership row is gone — get_current_principal
    # re-checks on every request, so access is revoked immediately, not at token expiry.
    blocked = client.get("/team/members", headers=member_headers)
    assert blocked.status_code == 401


def test_revoke_unknown_membership_404(client, make_principal):
    import uuid

    headers, _, _ = make_principal(role="admin")
    resp = client.post(f"/team/members/{uuid.uuid4()}/revoke", headers=headers)
    assert resp.status_code == 404
