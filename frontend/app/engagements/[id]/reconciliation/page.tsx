"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  apiGet,
  apiPost,
  apiPostForm,
  getToken,
  ApiError,
  type EngagementReport,
  type ExternalRecordBatch,
  type ImportPreviewResponse,
  type CommitExternalImportResponse,
  type ReconciliationRun,
  type ReconciliationMatch,
} from "@/lib/api";
import AppShell from "@/components/AppShell";
import { AlertIcon, UploadIcon, CheckCircleIcon, ArrowRightIcon, GridIcon } from "@/components/icons";

const REQUIRED_FIELDS = ["reference", "currency", "amount", "transaction_date"] as const;
const OPTIONAL_FIELDS = ["counterparty_name"] as const;
const ALL_FIELDS = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS] as const;

const FIELD_LABELS: Record<(typeof ALL_FIELDS)[number], string> = {
  reference: "Reference",
  currency: "Currency",
  amount: "Amount",
  transaction_date: "Transaction date",
  counterparty_name: "Counterparty (optional)",
};

const FIELD_GUESS_KEYWORDS: Record<(typeof ALL_FIELDS)[number], string[]> = {
  reference: ["reference", "ref", "narration", "description"],
  currency: ["currency", "ccy"],
  amount: ["amount", "value"],
  transaction_date: ["date"],
  counterparty_name: ["counterparty", "payee", "name"],
};

function parseCsvHeaderLine(line: string): string[] {
  return line
    .replace(/^﻿/, "")
    .split(",")
    .map((h) => h.trim().replace(/^"(.*)"$/, "$1"));
}

function guessMapping(headers: string[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const field of ALL_FIELDS) {
    const keywords = FIELD_GUESS_KEYWORDS[field];
    const match = headers.find((h) => keywords.some((kw) => h.toLowerCase().includes(kw)));
    result[field] = match ?? "";
  }
  return result;
}

function buildColumnMappingPayload(mapping: Record<string, string>): Record<string, string> {
  const payload: Record<string, string> = {};
  for (const field of REQUIRED_FIELDS) payload[field] = mapping[field];
  for (const field of OPTIONAL_FIELDS) if (mapping[field]) payload[field] = mapping[field];
  return payload;
}

const MATCH_STATUS_LABEL: Record<string, string> = {
  matched: "Matched",
  unmatched_transaction: "Unmatched — ledger side only",
  unmatched_external: "Unmatched — statement side only",
};

export default function ReconciliationPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [report, setReport] = useState<EngagementReport | null>(null);
  const [batches, setBatches] = useState<ExternalRecordBatch[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[] | null>(null);
  const [sourceLabel, setSourceLabel] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({
    reference: "",
    currency: "",
    amount: "",
    transaction_date: "",
    counterparty_name: "",
  });
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [uploadResult, setUploadResult] = useState<CommitExternalImportResponse | null>(null);

  const [selectedDatasetVersion, setSelectedDatasetVersion] = useState("");
  const [selectedBatch, setSelectedBatch] = useState("");
  const [run, setRun] = useState<ReconciliationRun | null>(null);
  const [matches, setMatches] = useState<ReconciliationMatch[] | null>(null);
  const [matchFilter, setMatchFilter] = useState<string>("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    load();
  }, [id]);

  function load() {
    apiGet<EngagementReport>(`/engagements/${id}/reports`).then(setReport).catch(() => {});
    apiGet<ExternalRecordBatch[]>(`/engagements/${id}/external-imports/batches`)
      .then((list) => {
        setBatches(list);
        if (list.length > 0 && !selectedBatch) setSelectedBatch(list[0].id);
      })
      .catch(() => {});
  }

  function handleFileChange(selected: File | null) {
    setFile(selected);
    setHeaders(null);
    setPreview(null);
    setUploadResult(null);
    if (!selected) return;
    selected
      .slice(0, 8192)
      .text()
      .then((chunk) => {
        const firstLine = chunk.split(/\r?\n/)[0] ?? "";
        const parsed = parseCsvHeaderLine(firstLine).filter((h) => h.length > 0);
        setHeaders(parsed);
        setMapping(guessMapping(parsed));
      })
      .catch(() => {});
  }

  async function runPreview(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !sourceLabel.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("column_mapping", JSON.stringify(buildColumnMappingPayload(mapping)));
      form.append("source_label", sourceLabel.trim());
      const result = await apiPostForm<ImportPreviewResponse>(`/engagements/${id}/external-imports/preview`, form);
      setPreview(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Preview failed.");
    } finally {
      setBusy(false);
    }
  }

  async function commitExternal() {
    if (!preview) return;
    setError(null);
    setBusy(true);
    try {
      const result = await apiPost<CommitExternalImportResponse>(
        `/engagements/${id}/external-imports/${preview.import_run_id}/commit`,
        {}
      );
      setUploadResult(result);
      setSelectedBatch(result.external_record_batch_id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Commit failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runReconciliation(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedDatasetVersion || !selectedBatch) return;
    setError(null);
    setBusy(true);
    setRun(null);
    setMatches(null);
    try {
      const result = await apiPost<ReconciliationRun>(`/engagements/${id}/reconciliation-runs`, {
        dataset_version_id: selectedDatasetVersion,
        external_record_batch_id: selectedBatch,
      });
      setRun(result);
      loadMatches(result.id, "");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reconciliation run failed.");
    } finally {
      setBusy(false);
    }
  }

  function loadMatches(runId: string, status: string) {
    setMatchFilter(status);
    const query = status ? `?match_status=${status}` : "";
    apiGet<ReconciliationMatch[]>(`/engagements/${id}/reconciliation-runs/${runId}/matches${query}`)
      .then(setMatches)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load matches."));
  }

  return (
    <AppShell title="Reconciliation" eyebrow="Match against a second source" icon={<GridIcon size={17} />}>
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      <p className="page-lede">
        Matches the ledger-side transactions you&rsquo;ve already committed against an
        independently-sourced second file — a bank or payment-gateway statement export.
        Exact match only in this build (same currency, reference, and amount on both
        sides) — no gateway/ERP connector exists, and no date-window or fee-tolerance
        matching yet. See <code>docs/reconciliation.md</code>.
      </p>

      <div className="card">
        <h3>1. Upload the second source (e.g. a bank statement)</h3>
        <form onSubmit={runPreview}>
          <label htmlFor="sourceLabel">Label for this source</label>
          <input
            id="sourceLabel"
            placeholder="e.g. GTBank NGN statement — Jan 2026"
            required
            value={sourceLabel}
            onChange={(e) => setSourceLabel(e.target.value)}
          />

          <label htmlFor="extFile">CSV file</label>
          <input
            id="extFile"
            type="file"
            accept=".csv,text/csv"
            required
            onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
          />

          {headers && (
            <>
              <p className="muted" style={{ marginTop: -6, marginBottom: 10 }}>
                Detected {headers.length} column(s) — matched where we could, check the rest.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 14px" }}>
                {ALL_FIELDS.map((field) => (
                  <div key={field}>
                    <label htmlFor={field}>
                      {FIELD_LABELS[field]}{" "}
                      {REQUIRED_FIELDS.includes(field as typeof REQUIRED_FIELDS[number]) && !mapping[field] && (
                        <span style={{ color: "var(--danger)" }}>— not matched</span>
                      )}
                    </label>
                    <select
                      id={field}
                      required={REQUIRED_FIELDS.includes(field as typeof REQUIRED_FIELDS[number])}
                      value={mapping[field]}
                      onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                    >
                      <option value="">
                        {REQUIRED_FIELDS.includes(field as typeof REQUIRED_FIELDS[number]) ? "Choose a column…" : "— not mapped —"}
                      </option>
                      {headers.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </>
          )}

          <button className="btn primary" type="submit" disabled={busy || !file || !headers}>
            {busy ? <span className="spinner" /> : null} Preview file
          </button>
        </form>

        {preview && !uploadResult && (
          <div style={{ marginTop: 16 }}>
            <div className="pill-row" style={{ marginBottom: 10 }}>
              <span className="pill" style={{ cursor: "default" }}>{preview.total_rows} row(s) read</span>
              <span className="pill" style={{ cursor: "default", color: "var(--success)", borderColor: "#bfe3cb" }}>
                {preview.valid_row_count} valid
              </span>
              {preview.error_row_count > 0 && (
                <span className="pill" style={{ cursor: "default", color: "var(--danger)", borderColor: "#f3c1c8" }}>
                  {preview.error_row_count} with errors
                </span>
              )}
            </div>
            <button className="btn primary" onClick={commitExternal} disabled={busy}>
              {busy ? <span className="spinner" /> : <UploadIcon size={14} />} Commit this source
            </button>
          </div>
        )}

        {uploadResult && (
          <div className="info-banner" style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 8 }}>
            <CheckCircleIcon size={15} />
            Committed as batch version #{uploadResult.version_number} ({uploadResult.row_count} row(s)).
          </div>
        )}
      </div>

      <div className="card">
        <h3>2. Run reconciliation</h3>
        {(!report || report.dataset_versions.length === 0 || !batches || batches.length === 0) && (
          <p className="muted">
            Need at least one committed dataset version (transactions) and one committed
            external batch (above) before a reconciliation run can be created.
          </p>
        )}
        {report && report.dataset_versions.length > 0 && batches && batches.length > 0 && (
          <form onSubmit={runReconciliation}>
            <div style={{ display: "flex", gap: 14 }}>
              <div style={{ flex: 1 }}>
                <label htmlFor="dsv">Ledger side (dataset version)</label>
                <select id="dsv" required value={selectedDatasetVersion} onChange={(e) => setSelectedDatasetVersion(e.target.value)}>
                  <option value="" disabled>
                    Choose…
                  </option>
                  {report.dataset_versions.map((dv) => (
                    <option key={dv.id} value={dv.id}>
                      Version #{dv.version_number} — committed {new Date(dv.committed_at).toLocaleString()}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label htmlFor="batch">Statement side (external batch)</label>
                <select id="batch" required value={selectedBatch} onChange={(e) => setSelectedBatch(e.target.value)}>
                  <option value="" disabled>
                    Choose…
                  </option>
                  {batches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.source_label} (v{b.version_number})
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <button className="btn primary" type="submit" disabled={busy || !selectedDatasetVersion || !selectedBatch}>
              {busy ? <span className="spinner" /> : null} Run exact-match reconciliation <ArrowRightIcon size={13} />
            </button>
          </form>
        )}
      </div>

      {run && (
        <div className="card">
          <h3>3. Results</h3>
          <div className="stat-grid">
            <div className="stat-card">
              <span className="muted" style={{ fontSize: 12 }}>Matched</span>
              <strong style={{ fontSize: 22, color: "var(--success)" }}>{run.matched_count}</strong>
            </div>
            <div className="stat-card">
              <span className="muted" style={{ fontSize: 12 }}>Unmatched (ledger side)</span>
              <strong style={{ fontSize: 22, color: "var(--danger)" }}>{run.unmatched_transaction_count}</strong>
            </div>
            <div className="stat-card">
              <span className="muted" style={{ fontSize: 12 }}>Unmatched (statement side)</span>
              <strong style={{ fontSize: 22, color: "var(--danger)" }}>{run.unmatched_external_count}</strong>
            </div>
          </div>

          <div className="pill-row" style={{ marginTop: 14, marginBottom: 10 }}>
            {["", "matched", "unmatched_transaction", "unmatched_external"].map((status) => (
              <button
                key={status || "all"}
                type="button"
                className="pill"
                style={{ fontWeight: matchFilter === status ? 700 : 400 }}
                onClick={() => loadMatches(run.id, status)}
              >
                {status ? MATCH_STATUS_LABEL[status] : "All"}
              </button>
            ))}
          </div>

          {matches && (
            <div className="card flush">
              <table>
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Basis</th>
                    <th>Ledger reference / amount</th>
                    <th>Statement reference / amount</th>
                  </tr>
                </thead>
                <tbody>
                  {matches.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <span className={`badge ${m.match_status === "matched" ? "status-confirmed" : "severity-medium"}`}>
                          {MATCH_STATUS_LABEL[m.match_status]}
                        </span>
                      </td>
                      <td className="mono" style={{ fontSize: 12 }}>{m.match_basis}</td>
                      <td className="mono" style={{ fontSize: 12.5 }}>
                        {m.transaction_record
                          ? `${m.transaction_record.invoice_reference} · ${m.transaction_record.currency} ${m.transaction_record.amount}`
                          : "—"}
                      </td>
                      <td className="mono" style={{ fontSize: 12.5 }}>
                        {m.external_record
                          ? `${m.external_record.reference} · ${m.external_record.currency} ${m.external_record.amount}`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                  {matches.length === 0 && (
                    <tr>
                      <td colSpan={4} className="muted">No rows for this filter.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
