"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  apiGet,
  apiPost,
  getToken,
  ApiError,
  type Finding,
  type TransactionRecordOut,
  type InvestigationRun,
} from "@/lib/api";
import AppShell from "@/components/AppShell";
import { AlertIcon, SparkleIcon, CheckCircleIcon, ClockIcon, FileSearchIcon } from "@/components/icons";

const SEVERITY_ICON: Record<string, typeof AlertIcon> = {
  high: AlertIcon,
  medium: ClockIcon,
  low: CheckCircleIcon,
};

const DISPOSITIONS = [
  { value: "confirmed", label: "Confirmed exception" },
  { value: "false_positive", label: "False positive" },
  { value: "needs_more_evidence", label: "Needs more evidence" },
];

export default function FindingDetailPage() {
  const { id, findingId } = useParams<{ id: string; findingId: string }>();
  const router = useRouter();

  const [finding, setFinding] = useState<Finding | null>(null);
  const [evidence, setEvidence] = useState<TransactionRecordOut[] | null>(null);
  const [investigations, setInvestigations] = useState<InvestigationRun[] | null>(null);
  const [status, setStatus] = useState(DISPOSITIONS[0].value);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [investigationError, setInvestigationError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [investigating, setInvestigating] = useState(false);
  const [saved, setSaved] = useState(false);

  async function load() {
    try {
      const [f, ev, inv] = await Promise.all([
        apiGet<Finding>(`/engagements/${id}/findings/${findingId}`),
        apiGet<TransactionRecordOut[]>(`/engagements/${id}/findings/${findingId}/evidence`),
        apiGet<InvestigationRun[]>(`/engagements/${id}/findings/${findingId}/investigations`),
      ]);
      setFinding(f);
      setEvidence(ev);
      setInvestigations(inv);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load finding.");
    }
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    load();
  }, [id, findingId]);

  async function requestInvestigation() {
    setInvestigationError(null);
    setInvestigating(true);
    try {
      await apiPost(`/engagements/${id}/findings/${findingId}/investigations`, {});
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setInvestigationError(
          "Claude investigation isn't configured in this environment (no ANTHROPIC_API_KEY / ANTHROPIC_MODEL_ID set)."
        );
      } else if (err instanceof ApiError && err.status === 429) {
        setInvestigationError("Daily investigation quota reached for this workspace. Try again tomorrow.");
      } else {
        setInvestigationError(err instanceof ApiError ? err.message : "Could not start investigation.");
      }
    } finally {
      setInvestigating(false);
    }
  }

  async function submitDisposition(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    setSaved(false);
    try {
      await apiPost(`/engagements/${id}/findings/${findingId}/disposition`, { status, rationale });
      setSaved(true);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record disposition.");
    } finally {
      setBusy(false);
    }
  }

  const latestInvestigation = investigations?.[investigations.length - 1] ?? null;

  return (
    <AppShell title="Finding detail" eyebrow="Review" icon={<FileSearchIcon size={17} />}>
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      {!finding && !error && <div className="skeleton" style={{ height: 120, marginBottom: 18 }} />}

      {finding && (
        <div className="card" style={{ display: "flex", gap: 16 }}>
          <div className={`finding-card-icon severity-${finding.severity}`} style={{ marginTop: 1 }}>
            {(() => {
              const SeverityIcon = SEVERITY_ICON[finding.severity] ?? AlertIcon;
              return <SeverityIcon size={18} />;
            })()}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <span className={`badge severity-${finding.severity}`}>{finding.severity}</span>
              <span className={`badge status-${finding.status}`}>{finding.status.replace(/_/g, " ")}</span>
            </div>
            <p style={{ fontSize: 14.5, color: "var(--ink-800)" }}>{finding.summary}</p>
            <p className="muted" style={{ marginBottom: 0 }}>
              This is a deterministic control result — a candidate requiring human review, not a
              proven exception.
            </p>
          </div>
        </div>
      )}

      {evidence && (
        <div className="card flush">
          <div className="card-header" style={{ padding: "18px 22px 10px" }}>
            <h3>Evidence ({evidence.length} record{evidence.length === 1 ? "" : "s"})</h3>
          </div>
          <table>
            <thead>
              <tr>
                <th>Row</th>
                <th>Supplier</th>
                <th>Invoice ref</th>
                <th>Currency</th>
                <th>Amount</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {evidence.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.source_row_number}</td>
                  <td>{r.supplier_name}</td>
                  <td>{r.invoice_reference}</td>
                  <td>{r.currency}</td>
                  <td className="mono">{r.amount}</td>
                  <td className="mono">{r.transaction_date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* AI investigation panel */}
      {finding && (
        <div className={investigations && investigations.length > 0 ? "ai-panel" : "card"}>
          <div className="ai-panel-header">
            <SparkleIcon size={17} className="mono" style={{ color: "var(--ai)" }} />
            <h3 style={{ marginBottom: 0 }}>Claude-assisted investigation</h3>
            <span className="badge ai-generated" style={{ marginLeft: "auto" }}>
              AI-generated
            </span>
          </div>
          <p className="muted" style={{ marginBottom: 14 }}>
            Optional. Claude investigates using read-only tools scoped to this engagement's data
            and reports findings — it never changes a record or closes this finding. Every claim
            below is checked against evidence actually returned during the run; unsupported claims
            are removed automatically.
          </p>

          {investigationError && (
            <div className="error-banner">
              <AlertIcon size={15} />
              {investigationError}
            </div>
          )}

          {!latestInvestigation && (
            <button className="btn primary" onClick={requestInvestigation} disabled={investigating}>
              {investigating ? <span className="spinner" /> : <SparkleIcon size={14} />}
              {investigating ? "Investigating…" : "Request AI investigation"}
            </button>
          )}

          {latestInvestigation && latestInvestigation.status === "pending" && (
            <p className="muted">
              <ClockIcon size={13} /> Investigation in progress…
            </p>
          )}

          {latestInvestigation && latestInvestigation.status === "failed" && (
            <div>
              <div className="error-banner">
                <AlertIcon size={15} />
                Investigation failed: {latestInvestigation.error_message}
              </div>
              <button className="btn secondary" onClick={requestInvestigation} disabled={investigating}>
                {investigating ? <span className="spinner dark" /> : null} Retry investigation
              </button>
            </div>
          )}

          {latestInvestigation && latestInvestigation.status === "completed" && latestInvestigation.result && (
            <div>
              <p style={{ fontSize: 14, color: "var(--ink-800)", marginBottom: 0 }}>
                {latestInvestigation.result.summary}
              </p>

              {latestInvestigation.result.observed_facts.length > 0 && (
                <>
                  <div className="ai-section-label">Observed facts</div>
                  {latestInvestigation.result.observed_facts.map((fact, i) => (
                    <div key={i} className="fact-item">
                      {fact.text}
                      <div style={{ marginTop: 5, display: "flex", gap: 5, flexWrap: "wrap" }}>
                        {fact.evidence_ids.map((eid) => (
                          <span key={eid} className="evidence-chip">
                            {eid.slice(0, 8)}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </>
              )}

              {latestInvestigation.result.inferences.length > 0 && (
                <>
                  <div className="ai-section-label">Inferences</div>
                  {latestInvestigation.result.inferences.map((inf, i) => (
                    <div key={i} className="fact-item">
                      {inf.text}
                      {inf.limitations && (
                        <div className="muted" style={{ marginTop: 3 }}>
                          Limitation: {inf.limitations}
                        </div>
                      )}
                    </div>
                  ))}
                </>
              )}

              {latestInvestigation.result.missing_checks.length > 0 && (
                <>
                  <div className="ai-section-label">Missing checks</div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5 }}>
                    {latestInvestigation.result.missing_checks.map((m, i) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </>
              )}

              {latestInvestigation.result.recommended_next_steps.length > 0 && (
                <>
                  <div className="ai-section-label">Recommended next steps</div>
                  {latestInvestigation.result.recommended_next_steps.map((step, i) => (
                    <div key={i} className="fact-item" style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                      <span>{step.text}</span>
                      {step.requires_human_approval && (
                        <span className="badge neutral" style={{ flexShrink: 0 }}>
                          needs approval
                        </span>
                      )}
                    </div>
                  ))}
                </>
              )}

              {latestInvestigation.result.uncertainties.length > 0 && (
                <>
                  <div className="ai-section-label">Uncertainties</div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, color: "var(--ink-600)" }}>
                    {latestInvestigation.result.uncertainties.map((u, i) => (
                      <li key={i}>{u}</li>
                    ))}
                  </ul>
                </>
              )}

              <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 10 }}>
                <button className="btn secondary sm" onClick={requestInvestigation} disabled={investigating}>
                  {investigating ? <span className="spinner dark" /> : null} Run another investigation
                </button>
                <span className="muted">
                  {investigations?.length} investigation{investigations?.length === 1 ? "" : "s"} run on this finding
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {finding && (
        <div className="card">
          <h3 style={{ marginBottom: 14 }}>Reviewer disposition</h3>
          {saved && (
            <div className="info-banner" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <CheckCircleIcon size={15} /> Saved and recorded in the audit log.
            </div>
          )}
          <form onSubmit={submitDisposition}>
            <label htmlFor="status">Decision</label>
            <select id="status" value={status} onChange={(e) => setStatus(e.target.value)}>
              {DISPOSITIONS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
            <label htmlFor="rationale">Rationale (required, recorded in the audit log)</label>
            <input id="rationale" required minLength={1} value={rationale} onChange={(e) => setRationale(e.target.value)} />
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? <span className="spinner" /> : null} Save disposition
            </button>
          </form>
        </div>
      )}

      <p className="muted">
        <Link href={`/engagements/${id}/findings`}>← Back to findings</Link>
      </p>
    </AppShell>
  );
}
