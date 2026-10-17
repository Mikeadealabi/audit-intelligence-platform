"""
Seed a demo tenant with a realistic engagement so the UI can be explored in a
browser without manually running the signup -> import -> control flow by hand.

Exercises the real HTTP API (not direct DB writes) so the seeded data goes
through the same validation, hashing, and control logic a real user would hit.

Usage (backend must already be running, e.g. `uvicorn app.main:app --port 8020`):
    python scripts/seed_demo.py
    python scripts/seed_demo.py --base-url http://localhost:8020

Idempotent: re-running reuses the demo account and skips re-seeding the
engagement if one with the same name already has findings.
"""

from __future__ import annotations

import argparse
import io
import json
import sys

import httpx

DEMO_EMAIL = "demo@auditplatform.example"
DEMO_PASSWORD = "DemoPass123!"
DEMO_TENANT_NAME = "Demo Audit Firm"
DEMO_ENGAGEMENT_NAME = "Demo: Nova MFB Lagos Branch Q3 Review"
DEMO_CLIENT_NAME = "Nova Microfinance Bank"

# Column headers already match the API's canonical field names, so the
# column_mapping sent below is the identity mapping.
DEMO_CSV = """supplier_name,invoice_reference,currency,amount,transaction_date
Bluewave Energy Ltd,INV-7701,NGN,1250000,2026-08-04
Prestige Interiors,INV-4420,NGN,95000,2026-08-06
Horizon Logistics,INV-5510,NGN,62000,2026-08-08
Horizon Logistics,INV-5522,NGN,71500,2026-08-19
Horizon Logistics,INV-5538,NGN,54000,2026-09-02
Acme Supplies Ltd,INV-1001,NGN,450000,2026-09-01
Acme Supplies Ltd,INV-1001,NGN,450000,2026-09-01
Zenith Traders,INV-2050,NGN,180000,2026-09-05
Zenith Traders,INV-2051,NGN,180000,2026-09-06
Zenith Traders,INV-2052,NGN,180000,2026-09-07
Globex Nigeria,INV-3300,NGN,90000,2026-09-10
"""

COLUMN_MAPPING = {
    "supplier_name": "supplier_name",
    "invoice_reference": "invoice_reference",
    "currency": "currency",
    "amount": "amount",
    "transaction_date": "transaction_date",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8020")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=10.0)

    try:
        client.get("/health").raise_for_status()
    except httpx.HTTPError as exc:
        print(f"Backend not reachable at {args.base_url}: {exc}", file=sys.stderr)
        print("Start it first: uvicorn app.main:app --port 8020", file=sys.stderr)
        return 1

    token = _get_or_create_account(client)
    auth = {"Authorization": f"Bearer {token}"}

    engagement_id = _get_or_create_engagement(client, auth)
    _seed_engagement_if_empty(client, auth, engagement_id)

    print()
    print("Demo account ready.")
    print(f"  Email:    {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")
    print(f"  Engagement: {DEMO_ENGAGEMENT_NAME} ({DEMO_CLIENT_NAME})")
    print()
    print("Open http://localhost:3090, sign in, and open that engagement.")
    return 0


def _get_or_create_account(client: httpx.Client) -> str:
    resp = client.post(
        "/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    if resp.status_code == 200:
        print("Demo account already exists, logging in.")
        return resp.json()["access_token"]

    resp = client.post(
        "/auth/signup",
        json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
            "tenant_name": DEMO_TENANT_NAME,
        },
    )
    resp.raise_for_status()
    print("Created demo account.")
    return resp.json()["access_token"]


def _get_or_create_engagement(client: httpx.Client, auth: dict) -> str:
    resp = client.get("/engagements", headers=auth)
    resp.raise_for_status()
    for eng in resp.json():
        if eng["name"] == DEMO_ENGAGEMENT_NAME:
            print(f"Reusing existing engagement {eng['id']}.")
            return eng["id"]

    resp = client.post(
        "/engagements",
        headers=auth,
        json={"name": DEMO_ENGAGEMENT_NAME, "client_name": DEMO_CLIENT_NAME},
    )
    resp.raise_for_status()
    eng_id = resp.json()["id"]
    print(f"Created engagement {eng_id}.")
    return eng_id


def _seed_engagement_if_empty(client: httpx.Client, auth: dict, engagement_id: str) -> None:
    resp = client.get(f"/engagements/{engagement_id}/findings", headers=auth)
    resp.raise_for_status()
    if resp.json():
        print("Engagement already has findings, skipping import/control seeding.")
        return

    files = {"file": ("demo_transactions.csv", io.BytesIO(DEMO_CSV.encode()), "text/csv")}
    data = {"column_mapping": json.dumps(COLUMN_MAPPING)}
    resp = client.post(
        f"/engagements/{engagement_id}/imports/preview",
        headers=auth,
        files=files,
        data=data,
    )
    resp.raise_for_status()
    preview = resp.json()
    print(f"Previewed import: {preview['valid_row_count']} valid rows, {preview['error_row_count']} errors.")

    resp = client.post(
        f"/engagements/{engagement_id}/imports/{preview['import_run_id']}/commit",
        headers=auth,
    )
    resp.raise_for_status()
    dataset_version_id = resp.json()["dataset_version_id"]
    print(f"Committed dataset version {dataset_version_id}.")

    resp = client.post(
        f"/engagements/{engagement_id}/control-runs",
        headers=auth,
        json={
            "control_code": "duplicate_invoice_candidates",
            "dataset_version_id": dataset_version_id,
            "parameters": {},
        },
    )
    resp.raise_for_status()
    print(f"Ran duplicate_invoice_candidates: {resp.json()['finding_count']} finding(s).")

    resp = client.post(
        f"/engagements/{engagement_id}/control-runs",
        headers=auth,
        json={
            "control_code": "threshold_splitting_candidates",
            "dataset_version_id": dataset_version_id,
            "parameters": {"threshold_amount": 500000, "currency": "NGN", "window_days": 7},
        },
    )
    resp.raise_for_status()
    print(f"Ran threshold_splitting_candidates: {resp.json()['finding_count']} finding(s).")


if __name__ == "__main__":
    raise SystemExit(main())
