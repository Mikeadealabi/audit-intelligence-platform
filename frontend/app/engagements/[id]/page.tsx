"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiGet, getToken, ApiError, type EngagementReport } from "@/lib/api";
import AppShell from "@/components/AppShell";
import StatCard from "@/components/StatCard";
import EmptyState from "@/components/EmptyState";
import { UploadIcon, FileSearchIcon, DocIcon, AlertIcon, ArrowRightIcon } from "@/components/icons";

export default function EngagementOverviewPage() {
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
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setError("Engagement not found (or you don't have access to it).");
        } else {
          setError("Could not load engagement.");
        }
      });
  }, [id]);

  const openCount = report?.findings.filter((f) => f.status === "open").length ?? 0;
  const highSeverityCount = report?.findings.filter((f) => f.severity === "high").length ?? 0;
  const recentFindings = report?.findings.slice(-5).reverse() ?? [];

  return (
    <AppShell title={report ? report.engagement_name : "Engagement"} eyebrow={report?.client_name}>
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      {!report && !error && (
        <div className="stat-grid">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ height: 84 }} />
          ))}
        </div>
      )}

      {report && (
        <>
          <div className="stat-grid">
            <StatCard label="Dataset versions" value={report.dataset_versions.length} />
            <StatCard label="Control runs" value={report.control_runs.length} />
            <StatCard label="Open findings" value={openCount} accent={openCount > 0} />
            <StatCard label="High severity" value={highSeverityCount} accent={highSeverityCount > 0} />
          </div>

          <div className="card">
            <div className="card-header">
              <h3>Quick actions</h3>
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Link className="btn primary" href={`/engagements/${id}/upload`}>
                <UploadIcon size={15} /> Upload transactions
              </Link>
              <Link className="btn secondary" href={`/engagements/${id}/findings`}>
                <FileSearchIcon size={15} /> Review findings
              </Link>
              <Link className="btn secondary" href={`/engagements/${id}/reports`}>
                <DocIcon size={15} /> View report
              </Link>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3>Recent findings</h3>
              {report.findings.length > 0 && (
                <Link href={`/engagements/${id}/findings`} className="muted" style={{ fontSize: 12.5, fontWeight: 600 }}>
                  View all →
                </Link>
              )}
            </div>

            {report.findings.length === 0 ? (
              <EmptyState
                icon={<FileSearchIcon size={20} />}
                title="No findings yet"
                description="Upload a CSV and run a control to see findings here."
                action={
                  <Link className="btn primary" href={`/engagements/${id}/upload`}>
                    Upload transactions
                  </Link>
                }
              />
            ) : (
              recentFindings.map((f) => (
                <Link key={f.id} href={`/engagements/${id}/findings/${f.id}`} className="finding-card">
                  <div className="finding-card-top">
                    <span className={`badge severity-${f.severity}`}>{f.severity}</span>
                    <span className={`badge status-${f.status}`}>{f.status.replace(/_/g, " ")}</span>
                  </div>
                  <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-700)" }}>{f.summary}</p>
                </Link>
              ))
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
