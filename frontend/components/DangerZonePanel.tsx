"use client";

import { useState } from "react";
import { apiPost, ApiError, type PurgeDataResponse } from "@/lib/api";
import { AlertIcon } from "@/components/icons";

export default function DangerZonePanel({
  engagementId,
  engagementName,
  onPurged,
}: {
  engagementId: string;
  engagementName: string;
  onPurged: (result: PurgeDataResponse) => void;
}) {
  const [confirmName, setConfirmName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PurgeDataResponse | null>(null);

  const canSubmit = confirmName.trim() === engagementName && !busy;

  async function purge() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiPost<PurgeDataResponse>(`/engagements/${engagementId}/purge-data`, {
        confirm_engagement_name: confirmName.trim(),
      });
      setResult(res);
      setConfirmName("");
      onPurged(res);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError("Only an admin on this tenant can purge engagement data.");
      } else {
        setError(err instanceof ApiError ? err.message : "Could not purge engagement data.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ borderColor: "var(--danger)" }}>
      <div className="card-header">
        <h3 style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <AlertIcon size={15} /> Danger zone
        </h3>
      </div>
      <p className="muted" style={{ marginTop: -4 }}>
        Permanently deletes the raw uploaded file bytes and the full original row content
        (<code>raw_row</code>) for every file imported into this engagement. Supplier names,
        amounts, findings, dispositions, sign-offs, and the full audit trail are <strong>not</strong>{" "}
        affected and remain exactly as they are today. This cannot be undone.
      </p>

      <label htmlFor="confirm-engagement-name">
        Type the engagement name (<strong>{engagementName}</strong>) to confirm
      </label>
      <input
        id="confirm-engagement-name"
        placeholder={engagementName}
        value={confirmName}
        onChange={(e) => setConfirmName(e.target.value)}
      />

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
        <button className="btn danger" onClick={purge} disabled={!canSubmit}>
          {busy ? <span className="spinner" /> : null} Purge raw data
        </button>
        {error && <span style={{ color: "var(--danger)", fontSize: 12.5 }}>{error}</span>}
        {result && !error && (
          <span style={{ color: "var(--success)", fontSize: 12.5 }}>
            Purged {result.source_file_count} file(s), {result.transaction_record_count} transaction
            record(s), {result.external_record_count} external record(s).
          </span>
        )}
      </div>
    </div>
  );
}
