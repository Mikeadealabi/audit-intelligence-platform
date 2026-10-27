"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiGet, apiPost, setToken, ApiError, type InvitePreview } from "@/lib/api";
import { ShieldIcon, AlertIcon } from "@/components/icons";
import ThemeToggle from "@/components/ThemeToggle";

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={null}>
      <AcceptInviteForm />
    </Suspense>
  );
}

function AcceptInviteForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) {
      setPreviewError("This invite link is missing its token.");
      return;
    }
    apiGet<InvitePreview>(`/invites/${token}`)
      .then(setPreview)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 410) {
          setPreviewError("This invite is no longer valid — it may have expired, been revoked, or already been used.");
        } else if (err instanceof ApiError && err.status === 404) {
          setPreviewError("This invite link isn't recognized.");
        } else {
          setPreviewError("Could not load this invite.");
        }
      });
  }, [token]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { access_token } = await apiPost<{ access_token: string }>(`/invites/${token}/accept`, { password });
      setToken(access_token);
      router.push("/engagements");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--paper)", display: "flex", alignItems: "center", justifyContent: "center", padding: 32, position: "relative" }}>
      <div style={{ position: "absolute", top: 18, right: 18 }}>
        <ThemeToggle variant="ghost" />
      </div>
      <div style={{ width: "100%", maxWidth: 380 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
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
            <ShieldIcon size={18} style={{ color: "#fff" }} />
          </div>
          <strong style={{ fontSize: 16 }}>Audit Intelligence Platform</strong>
        </div>

        {previewError && (
          <div className="error-banner">
            <AlertIcon size={15} />
            {previewError}
          </div>
        )}

        {preview && (
          <>
            <h2 style={{ fontSize: 22, marginBottom: 4 }}>You're invited</h2>
            <p className="muted" style={{ marginBottom: 22 }}>
              Join <strong>{preview.tenant_name}</strong> as <strong>{preview.role}</strong>. Set a
              password to create your account.
            </p>

            {error && (
              <div className="error-banner">
                <AlertIcon size={15} />
                {error}
              </div>
            )}

            <form onSubmit={submit}>
              <label htmlFor="email">Email</label>
              <input id="email" value={preview.email} disabled />

              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                required
                minLength={10}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <p className="muted" style={{ marginTop: -6, marginBottom: 14 }}>At least 10 characters.</p>

              <button className="btn primary" type="submit" disabled={busy} style={{ width: "100%", padding: "10px 15px" }}>
                {busy ? <span className="spinner" /> : null}
                {busy ? "Please wait…" : "Accept invite & sign in"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
