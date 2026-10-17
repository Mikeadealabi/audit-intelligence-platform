# Data Dictionary

## Status

Reflects tables actually created by the Alembic migration in this repo
(`backend/alembic/versions/0001_initial.py`). Entities from the full target model that
are **not yet created** are listed at the bottom so this file doesn't imply more exists
than does.

## Conventions

- All primary keys are `UUID` (not sequential integers) — avoids leaking record counts
  and makes IDOR guessing infeasible.
- All money columns are `NUMERIC(18,2)` with an explicit `currency` column alongside —
  never a float, never an implicit currency.
- All tables have `created_at` (UTC). Mutable tables also have `updated_at`.
- `tenant_id` is denormalized onto every table that is reachable from a tenant, even
  where it could be derived through a join, specifically so every query can filter on
  it directly without relying on a join being written correctly.

## Tables (implemented)

### tenant
`id, name, created_at`

### app_user
`id, email (unique), password_hash, created_at`

### tenant_membership
`id, tenant_id -> tenant, user_id -> app_user, role (member|admin), created_at`
Unique on `(tenant_id, user_id)`.

### engagement
`id, tenant_id -> tenant, name, client_name, status (active|closed), created_by -> app_user, created_at`

### source_file
`id, tenant_id, engagement_id -> engagement, uploaded_by -> app_user, original_filename, storage_path, sha256_hash, byte_size, content_type, created_at`
The uploaded file is written once, hashed, and never overwritten.

### import_run
`id, tenant_id, engagement_id, source_file_id -> source_file, column_mapping (JSON), source_label (nullable), status (pending|previewed|committed|rejected), row_count, error_count, created_by, created_at`
`column_mapping` records exactly which source column fed which canonical field —
required to reproduce a finding later. `source_label` is only used by the
external-record (reconciliation) import flow — a free-text caller-supplied label,
never a real connector identity; null for the transaction-record import flow. See
`docs/reconciliation.md`.

### dataset_version
`id, tenant_id, engagement_id, import_run_id -> import_run (unique), version_number, source_file_sha256, mapping_snapshot (JSON), committed_by, committed_at`
Created exactly once, when an `import_run` is committed. Immutable: no update
endpoint exists for this table. `version_number` is per-engagement and monotonically
increasing.

### transaction_record
`id, tenant_id, engagement_id, dataset_version_id -> dataset_version, source_row_number, supplier_name, invoice_reference, currency, amount (NUMERIC 18,2), transaction_date, tax_category (nullable), recorded_vat_amount (NUMERIC 18,2, nullable), recorded_wht_amount (NUMERIC 18,2, nullable), raw_row (JSON), created_at`
`raw_row` keeps the original mapped values for provenance even though only a subset
is promoted to typed columns in this slice. The three tax fields are **optional** —
`NULL` unless the source file's column mapping actually maps a column to them (see
`app/services/csv_parser.py::OPTIONAL_CANONICAL_FIELDS`); this platform never
computes or fills in a tax amount itself, only compares a recorded one against an
expected one in `tax_calculation_variance` (`docs/control-library.md`).

### external_record_batch
`id, tenant_id, engagement_id, import_run_id -> import_run (unique), source_label, version_number, source_file_sha256, mapping_snapshot (JSON), committed_by, committed_at`
The reconciliation subsystem's second, independently-sourced data source — the
external-record mirror of `dataset_version`. `version_number` is its own
per-engagement sequence, independent of `dataset_version.version_number`. See
`docs/reconciliation.md`.

### external_record
`id, tenant_id, engagement_id, external_record_batch_id -> external_record_batch, source_row_number, counterparty_name (nullable), reference (nullable), currency (nullable), amount (NUMERIC 18,2, nullable), transaction_date (nullable), raw_row (JSON), created_at`
The external-record mirror of `transaction_record`. `reference` is matched
against `transaction_record.invoice_reference` during reconciliation.

### reconciliation_run
`id, tenant_id, engagement_id, dataset_version_id -> dataset_version, external_record_batch_id -> external_record_batch, method, status, started_at, finished_at, run_by, matched_count, unmatched_transaction_count, unmatched_external_count, parameters (JSON)`
One execution of matching a `dataset_version` against an `external_record_batch`.
`method` and `parameters` exist so a future tolerance-based/fuzzy method can be
added without a schema change — only `"exact_match"` has an implementation
today. See `docs/reconciliation.md`.

### reconciliation_match
`id, tenant_id, engagement_id, reconciliation_run_id -> reconciliation_run, transaction_record_id (nullable), external_record_id (nullable), match_status (matched|unmatched_transaction|unmatched_external), match_basis (nullable), created_at`
One row per outcome: a matched pair (both FKs set) or a one-sided unmatched
record (exactly one FK set). `match_basis` always explains why — see
`docs/reconciliation.md`.

### control_definition
`id, code (unique, e.g. "duplicate_invoice_candidates"), name, description, created_at`

### control_version
`id, control_definition_id -> control_definition, version_number, logic_doc_ref, parameters (JSON), created_at`
Unique on `(control_definition_id, version_number)`. `docs/control-library.md`
describes what each version actually does — this row is metadata, not code.

### control_run
`id, tenant_id, engagement_id, dataset_version_id -> dataset_version, control_version_id -> control_version, status (completed|failed), started_at, finished_at, run_by, finding_count, skipped_row_count, parameters (JSON)`
`skipped_row_count` is rows excluded from evaluation because a required field was
missing — tracked so "0 findings" and "couldn't evaluate most rows" are distinguishable.
`parameters` is the exact configuration the caller supplied for this specific run
(e.g. `threshold_splitting_candidates`'s `threshold_amount`/`currency`/`window_days`)
— stored per-run rather than on `control_version` so different tenants/engagements
can use different thresholds without each needing its own control version. See
`docs/control-library.md`.

### finding
`id, tenant_id, engagement_id, control_run_id -> control_run, severity (low|medium|high), status (open|confirmed|false_positive|needs_more_evidence), summary, evidence_record_ids (JSON array of transaction_record.id), created_at`
`status` starts at `open` and only changes through a reviewer disposition, which is
itself an `audit_event`.

### investigation_run
`id, tenant_id, engagement_id, finding_id -> finding, status (pending|completed|failed), model_id, requested_by, requested_at, completed_at, result (JSON, nullable), tool_call_log (JSON array), token_usage (JSON), error_message (nullable)`
`result` is the grounded, schema-validated `InvestigationResult` (see
`docs/claude-tool-contract.md`) — null until `status = "completed"`. `tool_call_log`
is a redacted record of every tool call made (name, arguments, a safe summary, not
full record payloads). See `docs/claude-tool-contract.md` for the full contract.

### control_configuration
`id, tenant_id, engagement_id -> engagement, control_code, enabled, parameters (JSON), updated_by -> app_user, updated_at`
Unique on `(engagement_id, control_code)`. Drives auto-run-on-commit (see
`app/services/control_automation.py` and `docs/control-library.md`) — one row per
control a firm has opted into automating for a given engagement, with whatever
`parameters` that control needs stored the same way a manual `control_run.parameters`
is. Changing it is audited (`control_configuration.updated`).

### audit_event
`id, tenant_id, engagement_id (nullable), actor_user_id (nullable for system events), event_type, payload (JSON, redacted — see below), created_at`
Insert-only at the application layer (no update/delete route exists for this table)
**and at the database level** — a trigger (`backend/app/db_triggers.py`, applied by
migration `f2a72435b50d`) rejects any `UPDATE`/`DELETE` on this table outright, not
just "no route for it." `payload` must never contain a password, token, or full
`raw_row` dump — only identifiers and the specific fields relevant to the event
(e.g. a finding's new status, not every field on it).

## Entities in the target model NOT yet created

`SupplierRecord` (as its own entity — supplier is currently just a text field on
`transaction_record`), `EvidenceItem` (evidence is currently just the list of
`transaction_record.id` on a finding, not a richer entity), `CaseEvent` (case
commentary/assignment beyond a single disposition), `ReviewDecision` (currently
folded into `finding.status` + an `audit_event`, not a separate table with its own
rationale field — this is a known simplification to revisit once review workflow
needs more than one disposition per finding), `PolicyVersion` (needed once an
approval-policy-exception control is built — `check_approval_against_policy`
already exists as a Claude tool and always reports itself unsupported until this
table does).
