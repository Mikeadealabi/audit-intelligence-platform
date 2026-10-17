from sqlalchemy import delete

from app.models import TenantMembership
from app.services.rate_limit import login_rate_limiter


def test_signup_creates_tenant_and_returns_token(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "owner@example.com", "password": "correct-horse-battery", "tenant_name": "Acme Audit Firm"},
    )
    assert resp.status_code == 201
    assert "access_token" in resp.json()


def test_signup_duplicate_email_rejected(client):
    body = {"email": "dup@example.com", "password": "correct-horse-battery", "tenant_name": "Firm A"}
    assert client.post("/auth/signup", json=body).status_code == 201
    resp = client.post("/auth/signup", json=body)
    assert resp.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post(
        "/auth/signup",
        json={"email": "user@example.com", "password": "correct-horse-battery", "tenant_name": "Firm"},
    )
    resp = client.post("/auth/login", json={"email": "user@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_correct_password_returns_usable_token(client):
    client.post(
        "/auth/signup",
        json={"email": "user2@example.com", "password": "correct-horse-battery", "tenant_name": "Firm"},
    )
    login_resp = client.post("/auth/login", json={"email": "user2@example.com", "password": "correct-horse-battery"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    me_resp = client.get("/engagements", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200


def test_request_without_token_rejected(client):
    resp = client.get("/engagements")
    assert resp.status_code in (401, 403)


def test_login_rate_limited_after_repeated_attempts(client):
    login_rate_limiter._events.clear()  # isolate from whatever other tests did to the shared limiter
    email = "ratelimit-target@example.com"
    client.post(
        "/auth/signup",
        json={"email": email, "password": "correct-horse-battery", "tenant_name": "Firm"},
    )

    for _ in range(10):
        resp = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
        assert resp.status_code == 401

    blocked = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
    assert blocked.status_code == 429

    # A different email from the same client is unaffected — the limit is per key.
    other = client.post("/auth/login", json={"email": "someone-else@example.com", "password": "wrong"})
    assert other.status_code == 401


def test_revoked_membership_rejected_immediately(client, db):
    signup = client.post(
        "/auth/signup",
        json={"email": "revoked@example.com", "password": "correct-horse-battery", "tenant_name": "Firm"},
    )
    token = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/engagements", headers=headers).status_code == 200

    # Simulate revocation: delete the membership row directly, as an admin action
    # would. The already-issued JWT must stop working immediately, not at expiry.
    db.execute(delete(TenantMembership))
    db.commit()

    assert client.get("/engagements", headers=headers).status_code == 401
