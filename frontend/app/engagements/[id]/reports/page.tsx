"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiGet, getToken, ApiError, type EngagementReport } from "@/lib/api";
import AppShell from "@/components/AppShell";
import EmptyState from "@/components/EmptyState";
import { AlertIcon, DocIcon, SparkleIcon } from "@/components/icons";

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [report, setReport] = useState<EngagementReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    apiGet<EngagementReport>(`/engagements/${id}/reports`)
      .then(setReport)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load report."));
  }, [id]);

  return (
    <AppShell
      title="Engagement report"
      eyebrow="Evidence-backed export"
      actions={
        report && (
          <button className="btn secondary" onClick={() => window.print()}>
            Print / save as PDF
          </button>
        )
      }
    >
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      {!report && !error && <div className="skeleton" style={{ height: 200 }} />}

      {report && (
        <>
          <div className="card">
            <h2 style={{ marginBottom: 2 }}>{report.engagement_name}</h2>
            <p className="muted" style={{ marginBottom: 10 }}>
              {report.client_name} · generated {new Date(report.generated_at).toLocaleString()}
            </p>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "var(--ink-600)" }}>
              {report.limitations.map((l, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  {l}
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h3>Dataset versions ({report.dataset_versions.length})</h3>
            {report.dataset_versions.length === 0 ? (
              <p className="muted">None committed yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Source file SHA-256</th>
                    <th>Committed</th>
                  </tr>
                </thead>
                <tbody>
                  {report.dataset_versions.map((dv) => (
                    <tr key={dv.id}>
                      <td>#{dv.version_number}</td>
                      <td className="mono" style={{ fontSize: 11.5 }}>
                        {dv.source_file_sha256.slice(0, 16)}…
                      </td>
                      <td className="mono">{new Date(dv.committed_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card">
            <h3>Control runs ({report.control_runs.length})</h3>
            {report.control_runs.length === 0 ? (
              <p className="muted">None run yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Control</th>
                    <th>Version</th>
                    <th>Dataset</th>
                    <th>Findings</th>
                    <th>Skipped rows</th>
                    <th>Parameters</th>
                  </tr>
                </thead>
                <tbody>
                  {report.control_runs.map((cr) => (
                    <tr key={cr.id}>
                      <td>{cr.control_name}</td>
                      <td className="mono">v{cr.control_version}</td>
                      <td>#{cr.dataset_version_number}</td>
                      <td className="mono">{cr.finding_count}</td>
                      <td className="mono">{cr.skipped_row_count}</td>
                      <td className="mono" style={{ fontSize: 11 }}>
                        {Object.keys(cr.parameters).length > 0 ? JSON.stringify(cr.parameters) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card">
            <h3>Findings ({report.findings.length})</h3>
            {report.findings.length === 0 ? (
              <EmptyState icon={<DocIcon size={20} />} title="No findings in this engagement yet" />
            ) : (
              report.findings.map((f) => (
                <div key={f.id} className="finding-card" style={{ cursor: "default" }}>
                  <div className="finding-card-top">
                    <span className={`badge severity-${f.severity}`}>{f.severity}</span>
                    <span className={`badge status-${f.status}`}>{f.status.replace(/_/g, " ")}</span>
                    <span className="muted" style={{ marginLeft: "auto", fontSize: 11.5 }}>
                      {f.control_code} v{f.control_version} · dataset #{f.dataset_version_number}
                    </span>
                  </div>
                  <p style={{ margin: "0 0 8px", fontSize: 13.5 }}>{f.summary}</p>

                  {f.disposition && (
                    <div style={{ fontSize: 12.5, color: "var(--ink-600)", marginBottom: 6 }}>
                      <strong>Reviewer decision:</strong> {f.disposition.status.replace(/_/g, " ")} —{" "}
                      {f.disposition.rationale}{" "}
                      <span className="muted">({new Date(f.disposition.recorded_at).toLocaleDateString()})</span>
                    </div>
                  )}

                  {f.latest_investigation?.result && (
                    <div style={{ fontSize: 12.5, color: "var(--ink-600)", display: "flex", gap: 6, alignItems: "flex-start" }}>
                      <SparkleIcon size={13} style={{ color: "var(--ai)", marginTop: 1, flexShrink: 0 }} />
                      <span>
                        <strong>AI investigation summary:</strong> {f.latest_investigation.result.summary}
                      </span>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
