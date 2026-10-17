"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost, setToken, ApiError } from "@/lib/api";
import { ShieldIcon, AlertIcon, CheckCircleIcon, LockIcon, FileSearchIcon } from "@/components/icons";
import ThemeToggle from "@/components/ThemeToggle";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/signup";
      const body =
        mode === "login" ? { email, password } : { email, password, tenant_name: tenantName };
      const { access_token } = await apiPost<{ access_token: string }>(path, body);
      setToken(access_token);
      router.push("/engagements");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page" style={{ minHeight: "100vh", background: "var(--paper)" }}>
      <div
        className="login-hero"
        style={{
          background: "linear-gradient(175deg, var(--ink-950), var(--ink-800) 75%)",
          color: "#fff",
          padding: "56px 56px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: 10,
              background: "linear-gradient(135deg, var(--accent-500), var(--accent-700))",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <ShieldIcon size={18} />
          </div>
          <strong style={{ fontSize: 16 }}>Audit Intelligence Platform</strong>
        </div>

        <div style={{ margin: "auto 0", maxWidth: 440 }}>
          <h1 style={{ color: "#fff", fontSize: 34, lineHeight: 1.2, marginBottom: 14 }}>
            Evidence-grounded audit intelligence.
          </h1>
          <p style={{ color: "var(--ink-300)", fontSize: 15, lineHeight: 1.6 }}>
            Upload transaction data, run versioned deterministic controls, and route
            every finding through human review with a full evidence trail — with
            optional Claude-assisted investigation that never acts without you.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 32 }}>
            {[
              { icon: <CheckCircleIcon size={16} />, text: "Deterministic controls, not AI guesses, drive every finding" },
              { icon: <FileSearchIcon size={16} />, text: "Every claim traces back to source rows and dataset version" },
              { icon: <LockIcon size={16} />, text: "Tenant-isolated, append-only, database-enforced audit log" },
            ].map((item) => (
              <div key={item.text} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <span style={{ color: "var(--accent-500)", marginTop: 1 }}>{item.icon}</span>
                <span style={{ fontSize: 13.5, color: "var(--ink-200)" }}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        <p style={{ color: "var(--ink-500)", fontSize: 11.5 }}>
          Development build — a vertical slice, not a finished product.
        </p>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 32, position: "relative" }}>
        <div style={{ position: "absolute", top: 18, right: 18 }}>
          <ThemeToggle variant="ghost" />
        </div>
        <div style={{ width: "100%", maxWidth: 380 }}>
          <h2 style={{ fontSize: 22, marginBottom: 4 }}>
            {mode === "login" ? "Welcome back" : "Create your firm workspace"}
          </h2>
          <p className="muted" style={{ marginBottom: 22 }}>
            {mode === "login" ? "Sign in to continue." : "No account yet — set one up in a few seconds."}
          </p>

          <div style={{ display: "flex", gap: 6, marginBottom: 20, background: "var(--surface-sunken)", padding: 4, borderRadius: "var(--radius-md)" }}>
            <button
              type="button"
              onClick={() => setMode("login")}
              className="btn ghost"
              style={{
                flex: 1,
                background: mode === "login" ? "var(--surface)" : "transparent",
                boxShadow: mode === "login" ? "var(--shadow-sm)" : "none",
                color: mode === "login" ? "var(--ink-950)" : "var(--ink-500)",
              }}
            >
              Sign in
            </button>
            <button
              type="button"
              onClick={() => setMode("signup")}
              className="btn ghost"
              style={{
                flex: 1,
                background: mode === "signup" ? "var(--surface)" : "transparent",
                boxShadow: mode === "signup" ? "var(--shadow-sm)" : "none",
                color: mode === "signup" ? "var(--ink-950)" : "var(--ink-500)",
              }}
            >
              Create workspace
            </button>
          </div>

          {error && (
            <div className="error-banner">
              <AlertIcon size={15} />
              {error}
            </div>
          )}

          <form onSubmit={submit}>
            <label htmlFor="email">Work email</label>
            <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />

            {mode === "signup" && (
              <>
                <label htmlFor="tenantName">Firm / workspace name</label>
                <input id="tenantName" required value={tenantName} onChange={(e) => setTenantName(e.target.value)} />
              </>
            )}

            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              required
              minLength={mode === "signup" ? 10 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {mode === "signup" && <p className="muted" style={{ marginTop: -6, marginBottom: 14 }}>At least 10 characters.</p>}

            <button className="btn primary" type="submit" disabled={busy} style={{ width: "100%", padding: "10px 15px" }}>
              {busy ? <span className="spinner" /> : null}
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create workspace"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
