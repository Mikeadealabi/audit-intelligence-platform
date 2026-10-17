import io
import json

from app.config import settings
from app.deps import get_llm_provider
from app.main import app
from app.services.llm.provider import InvestigationOutcome, ProviderError, ToolCallRecord

MAPPING = json.dumps(
    {
        "supplier_name": "Supplier",
        "invoice_reference": "InvoiceRef",
        "currency": "Currency",
        "amount": "Amount",
        "transaction_date": "Date",
    }
)


class FakeProvider:
    """Test double standing in for the real Anthropic call. It runs the REAL tool
    executor (so tenant scoping / DB access in app/services/llm/tools.py is
    exercised for real) but the "model" behavior — which tools to call and what
    the final answer says — is scripted by the test."""

    def __init__(self, *, tool_calls: list[tuple[str, dict]], result: dict, input_tokens: int = 10, output_tokens: int = 20):
        self._tool_calls = tool_calls
        self._result_json = json.dumps(result)
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    def investigate(self, *, system_prompt, user_message, tools, tool_executor, output_schema, max_tool_turns):
        records = []
        for name, args in self._tool_calls:
            outcome = tool_executor(name, args)
            records.append(
                ToolCallRecord(
                    tool_name=name,
                    arguments=args,
                    result_summary=outcome.summary,
                    is_error=outcome.is_error,
                    evidence_ids=outcome.evidence_ids,
                )
            )
        return InvestigationOutcome(
            raw_result_json=self._result_json,
            tool_calls=records,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
        )


class FailingProvider:
    def investigate(self, **kwargs):
        raise ProviderError("simulated provider timeout")


def _csv_bytes(rows: list[str]) -> bytes:
    header = "Supplier,InvoiceRef,Currency,Amount,Date"
    return ("\n".join([header, *rows])).encode("utf-8")


def _finding_with_evidence(client, headers) -> tuple[str, str, list[str]]:
    """Creates an engagement, commits a dataset with a duplicate pair, runs the
    duplicate-invoice control, and returns (engagement_id, finding_id, evidence_ids)."""
    engagement_id = client.post(
        "/engagements", json={"name": "FY2026 Audit", "client_name": "Acme Ltd"}, headers=headers
    ).json()["id"]

    data = _csv_bytes(["Acme,INV-1,NGN,1000.00,2026-01-01", "Acme,INV-1,NGN,1000.00,2026-01-01"])
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
    finding = client.get(f"/engagements/{engagement_id}/findings", headers=headers).json()[0]
    return engagement_id, finding["id"], finding["evidence_record_ids"]


def test_investigation_returns_503_when_not_configured(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id, finding_id, _ = _finding_with_evidence(client, headers)

    assert settings.anthropic_api_key is None  # sanity check on the test environment

    resp = client.post(f"/engagements/{engagement_id}/findings/{finding_id}/investigations", headers=headers)
    assert resp.status_code == 503


def test_investigation_happy_path_grounds_fabricated_evidence(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id, finding_id, evidence_ids = _finding_with_evidence(client, headers)

    fake = FakeProvider(
        tool_calls=[("get_finding_context", {"finding_id": finding_id})],
        result={
            "summary": "Two identical invoice records were found.",
            "observed_facts": [
                {"text": "Real, grounded claim", "evidence_ids": evidence_ids},
                {
                    "text": "Fabricated claim citing evidence never returned",
                    "evidence_ids": ["00000000-0000-0000-0000-000000000000"],
                },
            ],
            "inferences": [],
            "missing_checks": ["No PO data available to cross-check"],
            "recommended_next_steps": [{"text": "Confirm with supplier", "requires_human_approval": True}],
            "uncertainties": [],
        },
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        resp = client.post(f"/engagements/{engagement_id}/findings/{finding_id}/investigations", headers=headers)
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "completed"
    assert len(body["result"]["observed_facts"]) == 1
    assert body["result"]["observed_facts"][0]["text"] == "Real, grounded claim"
    assert any("1 claim" in u for u in body["result"]["uncertainties"])
    assert body["token_usage"] == {"input_tokens": 10, "output_tokens": 20}
    assert len(body["tool_call_log"]) == 1
    assert body["tool_call_log"][0]["tool_name"] == "get_finding_context"


def test_investigation_provider_failure_marks_run_failed(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id, finding_id, _ = _finding_with_evidence(client, headers)

    app.dependency_overrides[get_llm_provider] = lambda: FailingProvider()
    try:
        resp = client.post(f"/engagements/{engagement_id}/findings/{finding_id}/investigations", headers=headers)
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert resp.status_code == 201  # the HTTP request succeeded; the *investigation* failed
    body = resp.json()
    assert body["status"] == "failed"
    assert "simulated provider timeout" in body["error_message"]
    assert body["result"] is None


def test_investigation_respects_daily_quota(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id, finding_id, _ = _finding_with_evidence(client, headers)

    original_limit = settings.llm_max_investigations_per_tenant_per_day
    settings.llm_max_investigations_per_tenant_per_day = 0
    app.dependency_overrides[get_llm_provider] = lambda: FailingProvider()
    try:
        resp = client.post(f"/engagements/{engagement_id}/findings/{finding_id}/investigations", headers=headers)
        assert resp.status_code == 429
    finally:
        settings.llm_max_investigations_per_tenant_per_day = original_limit
        app.dependency_overrides.pop(get_llm_provider, None)


def test_cross_tenant_cannot_access_investigation(client, make_principal):
    headers_a, _, _ = make_principal()
    headers_b, _, _ = make_principal()
    engagement_id, finding_id, evidence_ids = _finding_with_evidence(client, headers_a)

    fake = FakeProvider(
        tool_calls=[],
        result={
            "summary": "ok",
            "observed_facts": [],
            "inferences": [],
            "missing_checks": [],
            "recommended_next_steps": [],
            "uncertainties": [],
        },
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        created = client.post(
            f"/engagements/{engagement_id}/findings/{finding_id}/investigations", headers=headers_a
        ).json()
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    cross_tenant_list = client.get(
        f"/engagements/{engagement_id}/findings/{finding_id}/investigations", headers=headers_b
    )
    assert cross_tenant_list.status_code == 404  # engagement not found for tenant B

    cross_tenant_get = client.get(
        f"/engagements/{engagement_id}/findings/{finding_id}/investigations/{created['id']}", headers=headers_b
    )
    assert cross_tenant_get.status_code == 404


def test_list_and_get_investigation(client, make_principal):
    headers, _, _ = make_principal()
    engagement_id, finding_id, _ = _finding_with_evidence(client, headers)

    fake = FakeProvider(
        tool_calls=[],
        result={
            "summary": "ok",
            "observed_facts": [],
            "inferences": [],
            "missing_checks": [],
            "recommended_next_steps": [],
            "uncertainties": [],
        },
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        created = client.post(
            f"/engagements/{engagement_id}/findings/{finding_id}/investigations", headers=headers
        ).json()
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    listed = client.get(f"/engagements/{engagement_id}/findings/{finding_id}/investigations", headers=headers).json()
    assert len(listed) == 1

    fetched = client.get(
        f"/engagements/{engagement_id}/findings/{finding_id}/investigations/{created['id']}", headers=headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
