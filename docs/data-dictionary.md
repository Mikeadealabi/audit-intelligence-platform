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
`id, tenant_id, engagement_id, source_file_id -> source_file, column_mapping (JSON), status (pending|previewed|committed|rejected), row_count, error_count, created_by, created_at`
`column_mapping` records exactly which source column fed which canonical field —
required to reproduce a finding later.

### dataset_version
`id, tenant_id, engagement_id, import_run_id -> import_run (unique), version_number, source_file_sha256, mapping_snapshot (JSON), committed_by, committed_at`
Created exactly once, when an `import_run` is committed. Immutable: no update
endpoint exists for this table. `version_number` is per-engagement and monotonically
increasing.

### transaction_record
`id, tenant_id, engagement_id, dataset_version_id -> dataset_version, source_row_number, supplier_name, invoice_reference, currency, amount (NUMERIC 18,2), transaction_date, raw_row (JSON), created_at`
`raw_row` keeps the original mapped values for provenance even though only a subset
is promoted to typed columns in this slice.

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
