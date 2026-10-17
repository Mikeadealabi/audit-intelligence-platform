# Backup & Restore

## Status

**Not implemented.** No backup job, no restore drill has ever been run, because no
production environment exists yet. This file records the plan so it isn't invented
later under deadline pressure.

## Plan (to implement in Phase 6, before any pilot)

- Database: automated daily logical backups (`pg_dump`) plus continuous WAL archiving
  if the hosting provider supports point-in-time recovery; backups encrypted at rest.
- File storage: whatever the production object-storage provider's native
  versioning/replication offers, verified, not assumed.
- Restore drill: a documented, actually-executed procedure to restore into a scratch
  environment and verify row counts / a known finding reproduces identically —
  required before claiming backups "work."
- Retention of backups themselves follows the same retention schedule gate in
  `docs/privacy-and-compliance-checklist.md` — a backup outliving its source data's
  retention period is itself a compliance gap.

## Current reality

Local dev data lives in a Docker volume with no backup at all — losing it loses
nothing of record (it's development/test data only). Do not treat this file as
evidence that backups exist anywhere.
