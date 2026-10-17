"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiGet, getToken, ApiError, type EngagementReport, type EngagementAnalytics } from "@/lib/api";
import AppShell from "@/components/AppShell";
import StatCard from "@/components/StatCard";
import EmptyState from "@/components/EmptyState";
import BarChart from "@/components/BarChart";
import ControlAutomationPanel from "@/components/ControlAutomationPanel";
import {
  UploadIcon,
  FileSearchIcon,
  DocIcon,
  AlertIcon,
  ClockIcon,
  CheckCircleIcon,
  ShieldIcon,
  GridIcon,
  BarChartIcon,
  BuildingIcon,
} from "@/components/icons";

const SEVERITY_ICON: Record<string, typeof AlertIcon> = {
  high: AlertIcon,
  medium: ClockIcon,
  low: CheckCircleIcon,
};

export default function EngagementOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [report, setReport] = useState<EngagementReport | null>(null);
  const [analytics, setAnalytics] = useState<EngagementAnalytics | null>(null);
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
    apiGet<EngagementAnalytics>(`/engagements/${id}/analytics`)
      .then(setAnalytics)
      .catch(() => {
        // Analytics is a supplementary view — a failure here shouldn't block
        // the rest of the overview page from rendering.
      });
  }, [id]);

  const openCount = report?.findings.filter((f) => f.status === "open").length ?? 0;
  const highSeverityCount = report?.findings.filter((f) => f.severity === "high").length ?? 0;
  const recentFindings = report?.findings.slice(-5).reverse() ?? [];

  return (
    <AppShell
      title={report ? report.engagement_name : "Engagement"}
      eyebrow={report?.client_name}
      icon={<ShieldIcon size={17} />}
    >
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
            <StatCard
              label="Dataset versions"
              value={report.dataset_versions.length}
              icon={<GridIcon size={15} />}
            />
            <StatCard
              label="Control runs"
              value={report.control_runs.length}
              icon={<ShieldIcon size={15} />}
            />
            <StatCard
              label="Open findings"
              value={openCount}
              accent={openCount > 0}
              icon={<ClockIcon size={15} />}
            />
            <StatCard
              label="High severity"
              value={highSeverityCount}
              danger={highSeverityCount > 0}
              icon={<AlertIcon size={15} />}
            />
          </div>

          {analytics && (analytics.findings_by_severity.high + analytics.findings_by_severity.medium + analytics.findings_by_severity.low > 0 || analytics.supplier_summary.length > 0) && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
              <div className="card">
                <div className="card-header">
                  <h3 style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <BarChartIcon size={14} /> Findings by severity
                  </h3>
                </div>
                <BarChart
                  items={[
                    { label: "High", value: analytics.findings_by_severity.high ?? 0, color: "var(--severity-high)" },
                    { label: "Medium", value: analytics.findings_by_severity.medium ?? 0, color: "var(--severity-medium)" },
                    { label: "Low", value: analytics.findings_by_severity.low ?? 0, color: "var(--severity-low)" },
                  ]}
                />
              </div>

              <div className="card">
                <div className="card-header">
                  <h3 style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <BuildingIcon size={14} /> Top suppliers by transaction volume
                  </h3>
                  {analytics.supplier_summary.length > 0 && (
                    <Link href={`/engagements/${id}/suppliers`} className="muted" style={{ fontSize: 12.5, fontWeight: 600 }}>
                      View all →
                    </Link>
                  )}
                </div>
                {analytics.supplier_summary.length === 0 ? (
                  <p className="muted">No transaction data yet.</p>
                ) : (
                  <BarChart
                    items={analytics.supplier_summary.slice(0, 5).map((s) => {
                      const [currency, amount] = Object.entries(s.total_amount_by_currency)[0] ?? ["", "0"];
                      return {
                        label: s.supplier_name,
                        value: Number(amount),
                        color: s.flagged_transaction_count > 0 ? "var(--severity-high)" : "var(--accent-500)",
                        displayValue: `${currency} ${Number(amount).toLocaleString()}`,
                      };
                    })}
                  />
                )}
              </div>
            </div>
          )}

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
              <Link className="btn secondary" href={`/engagements/${id}/reconciliation`}>
                <GridIcon size={15} /> Reconciliation
              </Link>
            </div>
          </div>

          <ControlAutomationPanel engagementId={id} />

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
              recentFindings.map((f) => {
                const SeverityIcon = SEVERITY_ICON[f.severity] ?? AlertIcon;
                return (
                  <Link
                    key={f.id}
                    href={`/engagements/${id}/findings/${f.id}`}
                    className={`finding-card severity-${f.severity}`}
                  >
                    <div className={`finding-card-icon severity-${f.severity}`}>
                      <SeverityIcon size={16} />
                    </div>
                    <div className="finding-card-body">
                      <div className="finding-card-top">
                        <span className={`badge severity-${f.severity}`}>{f.severity}</span>
                        <span className={`badge status-${f.status}`}>{f.status.replace(/_/g, " ")}</span>
                      </div>
                      <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-700)" }}>{f.summary}</p>
                    </div>
                  </Link>
                );
              })
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
