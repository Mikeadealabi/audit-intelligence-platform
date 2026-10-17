# Incident Response

## Status

**Skeleton only — not an operational runbook, no on-call exists, nothing has been
tested.** Written now so Phase 6 has a starting point, not to imply readiness.

## Plan

1. **Detect**: today, detection is manual (no alerting/observability stack is wired
   up yet — a Phase 6 gap). Audit events and application error logs are the only
   signal that exists right now.
2. **Contain**: revoke affected sessions (delete/rotate `JWT_SECRET` invalidates all
   tokens immediately — a blunt instrument today, since no per-session revocation
   list exists yet), disable the affected tenant membership if a single account is
   compromised.
3. **Assess scope**: use `audit_event` rows to reconstruct what the affected
   principal actually accessed. This is only as good as the audit coverage — see
   `docs/threat-model.md` for known gaps (e.g. no DB-level immutability yet).
4. **Notify**: data-breach notification obligations under NDPA 2023 depend on facts
   this document cannot pre-judge; route to counsel per
   `docs/privacy-and-compliance-checklist.md` before any client notification goes
   out.
5. **Remediate & review**: fix root cause, add a regression test, update this
   document with what was actually learned (not hypothetically — only after a real
   drill or real incident).

No incident has occurred and no drill has been run against this plan yet.
