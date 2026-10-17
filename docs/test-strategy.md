# Test Strategy

## Status

Describes tests that actually exist in `backend/tests/` plus the target coverage for
later phases, clearly separated.

## Implemented (backend, pytest + a real Postgres)

- **Unit**: CSV parsing/validation edge cases (`test_csv_parser.py`) — bad encoding,
  missing required columns, extra columns, empty file, oversized file rejected before
  parsing, decimal/locale-formatted amounts, blank/malformed dates.
- **Unit**: duplicate-invoice control logic (`test_duplicate_invoice_control.py`) —
  see `docs/control-library.md` for the exact cases, including the Decimal-precision
  case.
- **Unit**: threshold-splitting control logic (`test_threshold_splitting_control.py`,
  13 cases) — missing/invalid parameters raise instead of silently defaulting,
  chain-clustering across a date gap, wrong-currency rows skipped not miscounted,
  single at-or-above-threshold transactions never flagged. See
  `docs/control-library.md`.
- **Integration**: full import flow (`test_import_flow.py`) — upload → preview →
  commit creates exactly one immutable `DatasetVersion` with the right hash and
  mapping snapshot; committing twice does not duplicate or mutate it.
- **Integration**: control run → findings (`test_control_run_flow.py`) — running a
  control version against a dataset version produces findings whose evidence IDs all
  resolve to real rows in that dataset version.
- **Security/integration**: tenant isolation (`test_tenant_isolation.py`) — a user in
  Tenant A gets 404 (not 403, to avoid confirming existence) for Tenant B's
  engagement, source file, dataset version, control run, and finding, by ID, across
  every router that exposes one of those resources.
- **Auth** (`test_auth.py`): login rejects wrong password, issues a token on success,
  the token's tenant claim is re-verified against a live `TenantMembership` row
  rather than trusted as-is, and repeated failed logins against the same email+IP
  are rate-limited (429) after 10 attempts without affecting other emails.
- **Security/integration**: audit-log DB-level immutability (`test_audit_immutability.py`)
  — a direct `UPDATE` or `DELETE` on `audit_event` is rejected by the database trigger
  itself, not just absent from the API surface.
- **Unit**: Claude investigation evidence grounding (`test_llm_schema.py`, 8 cases) —
  claims citing evidence IDs never returned by a tool call are dropped and counted
  in an uncertainty note; claims with a valid subset keep only the valid IDs.
- **Unit**: Claude investigation tools (`test_llm_tools.py`, 8 cases) — every tool is
  exercised directly against a real DB: tenant scoping (a tool executor scoped to
  tenant B returns nothing for tenant A's record IDs, not an error that would
  confirm existence), invalid-UUID and unknown-tool-name arguments return a
  structured error instead of crashing, `get_document_metadata` never includes
  `storage_path`, `check_approval_against_policy` always reports itself unsupported.
- **Integration**: full investigation request flow (`test_investigations.py`, 7 cases)
  — 503 when `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL_ID` aren't configured (the real
  case in this dev environment); against a `FakeProvider` test double (real tool
  execution, scripted model behaviour): a fabricated evidence ID gets stripped from
  the persisted result, a provider failure leaves the run `status="failed"` with no
  fabricated result, the daily quota returns 429 once exhausted, and cross-tenant
  access to another tenant's investigation is 404.
- **Integration**: report export (`test_reports.py`, 3 cases) — a report bundles the
  right dataset versions/control runs/findings/dispositions, an engagement with no
  activity yet returns empty lists rather than erroring, and cross-tenant access is
  404.

Run with `cd backend && pytest`. CI runs the same suite against a Postgres service
container — see `docs/deployment-runbook.md`. As of 2026-10-17: 88 tests, all passing.

## Not implemented yet (target for later phases)

- End-to-end browser tests (Playwright/Cypress) driving the actual Next.js UI —
  frontend exists but has not been exercised by an automated browser test in this
  slice, only `tsc --noEmit` / `next build`.
- Prompt-injection and model-evaluation tests against the **real** Anthropic API —
  the structural defenses are unit-tested (see `docs/claude-tool-contract.md`), but
  no adversarial eval has been run against a live model, since this environment has
  no API key configured. Do this before any pilot.
- Malicious-spreadsheet / XLSX-specific security tests — XLSX isn't parsed yet.
- Load/performance tests.
- Backup/restore drill (see `docs/backup-restore.md`).
- Dependency/SCA scanning in CI (not wired up yet — a gap, tracked here rather than
  silently assumed).
