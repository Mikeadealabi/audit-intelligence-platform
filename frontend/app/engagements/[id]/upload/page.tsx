"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  apiPostForm,
  apiPost,
  getToken,
  ApiError,
  type ImportPreviewResponse,
  type CommitImportResponse,
} from "@/lib/api";
import AppShell from "@/components/AppShell";
import { AlertIcon, UploadIcon, CheckCircleIcon, ArrowRightIcon } from "@/components/icons";

const CANONICAL_FIELDS = [
  "supplier_name",
  "invoice_reference",
  "currency",
  "amount",
  "transaction_date",
] as const;

function StepBadge({ n, done }: { n: number; done?: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 24,
        height: 24,
        borderRadius: "50%",
        background: done ? "var(--success-bg)" : "var(--accent-100)",
        color: done ? "var(--success)" : "var(--accent-600)",
        fontSize: 12,
        fontWeight: 700,
        marginRight: 10,
        flexShrink: 0,
      }}
    >
      {done ? <CheckCircleIcon size={14} /> : n}
    </span>
  );
}

export default function UploadPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({
    supplier_name: "Supplier",
    invoice_reference: "InvoiceRef",
    currency: "Currency",
    amount: "Amount",
    transaction_date: "Date",
  });
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [commitResult, setCommitResult] = useState<CommitImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [splitThreshold, setSplitThreshold] = useState("500000.00");
  const [splitCurrency, setSplitCurrency] = useState("NGN");
  const [splitWindowDays, setSplitWindowDays] = useState("3");

  useEffect(() => {
    if (!getToken()) router.push("/");
  }, []);

  async function runPreview(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setBusy(true);
    setPreview(null);
    setCommitResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("column_mapping", JSON.stringify(mapping));
      const result = await apiPostForm<ImportPreviewResponse>(`/engagements/${id}/imports/preview`, form);
      setPreview(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Preview failed.");
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!preview) return;
    setError(null);
    setBusy(true);
    try {
      const result = await apiPost<CommitImportResponse>(
        `/engagements/${id}/imports/${preview.import_run_id}/commit`,
        {}
      );
      setCommitResult(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Commit failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runControlAndGoToFindings(controlCode: string, parameters?: Record<string, string | number>) {
    if (!commitResult) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost(`/engagements/${id}/control-runs`, {
        dataset_version_id: commitResult.dataset_version_id,
        control_code: controlCode,
        parameters: parameters ?? null,
      });
      router.push(`/engagements/${id}/findings`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not run control.");
      setBusy(false);
    }
  }

  async function runThresholdSplitting(e: React.FormEvent) {
    e.preventDefault();
    await runControlAndGoToFindings("threshold_splitting_candidates", {
      threshold_amount: splitThreshold,
      currency: splitCurrency,
      window_days: Number(splitWindowDays),
    });
  }

  return (
    <AppShell title="Upload transactions" eyebrow="Import">
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
          <StepBadge n={1} />
          <h3 style={{ marginBottom: 0 }}>Choose file and map columns</h3>
        </div>
        <p className="muted" style={{ marginLeft: 34 }}>
          CSV only in this build (XLSX isn&rsquo;t implemented yet). Column names below
          must match your file&rsquo;s header row exactly.
        </p>
        <form onSubmit={runPreview} style={{ marginLeft: 34, marginTop: 14 }}>
          <label htmlFor="file">CSV file</label>
          <input
            id="file"
            type="file"
            accept=".csv,text/csv"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 14px" }}>
            {CANONICAL_FIELDS.map((field) => (
              <div key={field}>
                <label htmlFor={field} className="mono">
                  {field} <span style={{ color: "var(--ink-400)" }}>← source column</span>
                </label>
                <input
                  id={field}
                  required
                  value={mapping[field]}
                  onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <button className="btn primary" type="submit" disabled={busy || !file}>
            {busy && !preview ? <span className="spinner" /> : null}
            Preview file
          </button>
        </form>
      </div>

      {preview && (
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
            <StepBadge n={2} />
            <h3 style={{ marginBottom: 0 }}>Review and commit</h3>
          </div>
          <div style={{ marginLeft: 34 }}>
            <div className="pill-row" style={{ marginBottom: 14 }}>
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
            {preview.error_row_count > 0 && (
              <p className="muted" style={{ marginTop: -8 }}>
                Rows with errors will be excluded from the committed dataset version, not guessed at.
              </p>
            )}
            <div className="card flush" style={{ marginBottom: 16 }}>
              <table>
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Supplier</th>
                    <th>Invoice ref</th>
                    <th>Currency</th>
                    <th>Amount</th>
                    <th>Date</th>
                    <th>Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.sample_rows.map((r) => (
                    <tr key={r.row_number}>
                      <td className="mono">{r.row_number}</td>
                      <td>{r.mapped.supplier_name ?? "—"}</td>
                      <td>{r.mapped.invoice_reference ?? "—"}</td>
                      <td>{r.mapped.currency ?? "—"}</td>
                      <td className="mono">{r.mapped.amount ?? "—"}</td>
                      <td className="mono">{r.mapped.transaction_date ?? "—"}</td>
                      <td style={{ color: r.errors.length ? "var(--danger)" : undefined, fontSize: 12 }}>
                        {r.errors.join("; ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {!commitResult && (
              <button className="btn primary" onClick={commit} disabled={busy}>
                {busy ? <span className="spinner" /> : <UploadIcon size={14} />}
                Commit as dataset version
              </button>
            )}

            {commitResult && (
              <div>
                <div className="info-banner" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <CheckCircleIcon size={15} />
                  Committed as dataset version #{commitResult.version_number} ({commitResult.row_count} row(s)).
                </div>

                <div style={{ display: "flex", alignItems: "center", marginTop: 20, marginBottom: 10 }}>
                  <StepBadge n={3} />
                  <h3 style={{ marginBottom: 0 }}>Run a control</h3>
                </div>

                <div style={{ marginLeft: 34, display: "flex", flexDirection: "column", gap: 14 }}>
                  <div className="card" style={{ marginBottom: 0 }}>
                    <h3 style={{ fontSize: 13.5 }}>Duplicate invoice candidates</h3>
                    <p className="muted">No configuration needed — exact match on supplier, invoice reference, currency, amount, and date.</p>
                    <button
                      className="btn secondary"
                      onClick={() => runControlAndGoToFindings("duplicate_invoice_candidates")}
                      disabled={busy}
                    >
                      Run control <ArrowRightIcon size={13} />
                    </button>
                  </div>

                  <div className="card" style={{ marginBottom: 0 }}>
                    <h3 style={{ fontSize: 13.5 }}>Threshold-splitting candidates</h3>
                    <p className="muted">
                      No built-in default — set your firm&rsquo;s approval threshold. See{" "}
                      <code>docs/control-library.md</code> for what this does and doesn&rsquo;t catch.
                    </p>
                    <form onSubmit={runThresholdSplitting}>
                      <div style={{ display: "flex", gap: 10 }}>
                        <div style={{ flex: 2 }}>
                          <label htmlFor="splitThreshold">Approval threshold</label>
                          <input id="splitThreshold" required value={splitThreshold} onChange={(e) => setSplitThreshold(e.target.value)} />
                        </div>
                        <div style={{ flex: 1 }}>
                          <label htmlFor="splitCurrency">Currency</label>
                          <input id="splitCurrency" required value={splitCurrency} onChange={(e) => setSplitCurrency(e.target.value)} />
                        </div>
                        <div style={{ flex: 1 }}>
                          <label htmlFor="splitWindowDays">Window (days)</label>
                          <input
                            id="splitWindowDays"
                            type="number"
                            min={1}
                            required
                            value={splitWindowDays}
                            onChange={(e) => setSplitWindowDays(e.target.value)}
                          />
                        </div>
                      </div>
                      <button className="btn secondary" type="submit" disabled={busy}>
                        Run control <ArrowRightIcon size={13} />
                      </button>
                    </form>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
}
