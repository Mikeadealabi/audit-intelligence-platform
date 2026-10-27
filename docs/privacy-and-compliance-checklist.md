# Privacy & Compliance Checklist (pre-production gate)

## Status

None of the items below have been reviewed by qualified counsel or a Nigerian
tax/compliance professional. **This repository makes no claim of NDPA/NDPR compliance,
CBN compliance, FIRS compliance, ISO certification, or NDPC approval.** This checklist
exists so that gap is explicit and trackable, not to imply progress toward it.

## Must be resolved before any real client data touches this system

- [ ] Lawful basis for processing personal data found inside uploaded transaction
      files (employee names, beneficiary names, etc.) under NDPA 2023/NDPR.
- [ ] Data minimisation / purpose limitation review of what canonical fields are
      actually necessary vs. convenient.
- [ ] Retention schedule per data category, and who can trigger deletion. An
      admin-invokable manual purge now exists (`POST /engagements/{id}/purge-data`,
      2026-10-27 — see `docs/data-dictionary.md` and `DECISIONS.md`): it deletes raw
      uploaded file bytes and the full original `raw_row` content, while keeping
      canonical fields, findings, dispositions, sign-offs, and the audit trail
      intact. **This is a manual tool a firm invokes, not an automated retention
      schedule** — there is still no auto-expiry/cron job, and no policy engine
      deciding *when* something should be purged. That policy decision remains
      unresolved.
- [ ] Data-subject request process (access/correction/erasure) — not built.
- [ ] DPIA or equivalent assessment, if the firm's engagement involves higher-risk
      processing.
- [ ] Subprocessor list (hosting provider, any email/notification provider, the
      Anthropic API once Phase 5 ships) and data-transfer basis for each, including
      any cross-border transfer.
- [ ] Incident/breach notification process and owner — see
      `docs/incident-response.md` (currently a skeleton, not an operational runbook).
- [ ] Client confidentiality / engagement-letter language covering this tool's use,
      reviewed by the audit firm's own counsel.
- [ ] Audit methodology sign-off from the firm — this tool assists; it does not
      replace professional judgement or standards (e.g. ISA-aligned work programs).
- [ ] Tax-rate values (VAT 7.5%, WHT bands, PAYE bands) if ever used in a future
      control: must be reviewed and kept current by a Nigerian tax professional. They
      are modelled as configurable data (`PolicyVersion`-style tables), not constants,
      specifically so they can be corrected without a code change — but no such
      control exists yet and none should ship without that review.
- [ ] Hosting/region choice: choosing a Nigerian or any other data-residency region
      is an infrastructure decision, not a compliance certification by itself.

## Explicitly not claimed anywhere in this repo

NDPC approval, ISO 27001 (or any ISO) certification, SOC 2, CBN licensing/no-objection,
FIRS endorsement, legal compliance of any kind. If any of this text is found elsewhere
making such a claim, treat it as a bug and remove it.
