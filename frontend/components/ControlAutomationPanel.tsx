"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPut, ApiError, type ControlConfiguration } from "@/lib/api";

type Draft = { enabled: boolean; paramsText: string };

function defaultParamsJson(cfg: ControlConfiguration): string {
  if (Object.keys(cfg.parameters).length > 0) return JSON.stringify(cfg.parameters, null, 2);
  if (cfg.required_parameters_hint.length === 0) return "{}";
  const skeleton: Record<string, string> = {};
  for (const key of cfg.required_parameters_hint) skeleton[key] = "";
  return JSON.stringify(skeleton, null, 2);
}

export default function ControlAutomationPanel({ engagementId }: { engagementId: string }) {
  const [configs, setConfigs] = useState<ControlConfiguration[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [savedCode, setSavedCode] = useState<string | null>(null);

  useEffect(() => {
    load();
  }, [engagementId]);

  function load() {
    apiGet<ControlConfiguration[]>(`/engagements/${engagementId}/control-configurations`).then((list) => {
      setConfigs(list);
      setDrafts((prev) => {
        const next: Record<string, Draft> = {};
        for (const cfg of list) {
          // Preserve an in-progress edit for a control the user hasn't saved
          // yet; only seed from the server for ones we don't have a draft for.
          next[cfg.control_code] = prev[cfg.control_code] ?? {
            enabled: cfg.enabled,
            paramsText: defaultParamsJson(cfg),
          };
        }
        return next;
      });
    });
  }

  async function save(code: string) {
    const draft = drafts[code];
    if (!draft) return;
    setBusyCode(code);
    setErrors((e) => ({ ...e, [code]: "" }));
    setSavedCode(null);
    try {
      let parameters: Record<string, unknown> = {};
      if (draft.paramsText.trim()) {
        try {
          parameters = JSON.parse(draft.paramsText);
        } catch {
          throw new Error("Parameters must be valid JSON.");
        }
      }
      await apiPut<ControlConfiguration>(`/engagements/${engagementId}/control-configurations/${code}`, {
        enabled: draft.enabled,
        parameters,
      });
      setSavedCode(code);
      load();
    } catch (err) {
      setErrors((e) => ({
        ...e,
        [code]: err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Save failed.",
      }));
    } finally {
      setBusyCode(null);
    }
  }

  if (!configs) return null;

  return (
    <div className="card">
      <div className="card-header">
        <h3>Automated controls</h3>
      </div>
      <p className="muted" style={{ marginTop: -4 }}>
        An enabled control runs automatically every time a new dataset version is committed for
        this engagement — no need to trigger it by hand on the upload page. A control whose saved
        parameters are missing or invalid is <strong>skipped, not failed</strong>, on that commit —
        see the activity log for <code>control.autorun_skipped</code> events.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {configs.map((cfg) => {
          const draft = drafts[cfg.control_code];
          if (!draft) return null;
          return (
            <div key={cfg.control_code} className="card flush" style={{ padding: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
                <div>
                  <label
                    style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 600, fontSize: 13.5, marginBottom: 0 }}
                  >
                    <input
                      type="checkbox"
                      checked={draft.enabled}
                      onChange={(e) =>
                        setDrafts((d) => ({ ...d, [cfg.control_code]: { ...d[cfg.control_code], enabled: e.target.checked } }))
                      }
                      style={{ width: 16, marginBottom: 0 }}
                    />
                    {cfg.control_name}
                  </label>
                  <p className="muted" style={{ fontSize: 12.5, marginTop: 4, marginLeft: 24 }}>
                    {cfg.description}
                  </p>
                </div>
                <button
                  className="btn secondary sm"
                  onClick={() => save(cfg.control_code)}
                  disabled={busyCode === cfg.control_code}
                >
                  {busyCode === cfg.control_code ? <span className="spinner" /> : null} Save
                </button>
              </div>

              {cfg.required_parameters_hint.length > 0 && (
                <div style={{ marginLeft: 24, marginTop: 8 }}>
                  <label htmlFor={`params-${cfg.control_code}`} style={{ fontSize: 12 }}>
                    Parameters (JSON) — requires: {cfg.required_parameters_hint.join(", ")}
                  </label>
                  <textarea
                    id={`params-${cfg.control_code}`}
                    rows={3}
                    style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
                    value={draft.paramsText}
                    onChange={(e) =>
                      setDrafts((d) => ({ ...d, [cfg.control_code]: { ...d[cfg.control_code], paramsText: e.target.value } }))
                    }
                  />
                </div>
              )}

              {errors[cfg.control_code] && (
                <p style={{ color: "var(--danger)", fontSize: 12, marginLeft: 24, marginTop: 6, marginBottom: 0 }}>
                  {errors[cfg.control_code]}
                </p>
              )}
              {savedCode === cfg.control_code && !errors[cfg.control_code] && (
                <p style={{ color: "var(--success)", fontSize: 12, marginLeft: 24, marginTop: 6, marginBottom: 0 }}>
                  Saved.
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
