"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  apiGet,
  apiPost,
  getToken,
  ApiError,
  type TenantMember,
  type TenantInvite,
  type InviteCreateResponse,
  type TenantRole,
} from "@/lib/api";
import AppShell from "@/components/AppShell";
import { AlertIcon, UsersIcon } from "@/components/icons";

export default function TeamPage() {
  const router = useRouter();
  const [members, setMembers] = useState<TenantMember[] | null>(null);
  const [invites, setInvites] = useState<TenantInvite[] | null>(null);
  const [isAdmin, setIsAdmin] = useState(true); // optimistic — corrected to false on a 403 below
  const [error, setError] = useState<string | null>(null);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<TenantRole>("member");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [lastInvite, setLastInvite] = useState<InviteCreateResponse | null>(null);

  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    load();
  }, []);

  function load() {
    apiGet<TenantMember[]>("/team/members")
      .then(setMembers)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load team members."));
    apiGet<TenantInvite[]>("/team/invites")
      .then(setInvites)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setIsAdmin(false);
          setInvites([]);
        }
      });
  }

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviteError(null);
    setInviteBusy(true);
    setLastInvite(null);
    try {
      const invite = await apiPost<InviteCreateResponse>("/team/invites", { email: inviteEmail, role: inviteRole });
      setLastInvite(invite);
      setInviteEmail("");
      load();
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Could not create the invite.");
    } finally {
      setInviteBusy(false);
    }
  }

  async function revokeInvite(id: string) {
    setActionError(null);
    try {
      await apiPost(`/team/invites/${id}/revoke`, {});
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not revoke the invite.");
    }
  }

  async function removeMember(id: string) {
    setActionError(null);
    try {
      await apiPost(`/team/members/${id}/revoke`, {});
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setActionError("Only an admin on this tenant can remove a team member.");
      } else {
        setActionError(err instanceof ApiError ? err.message : "Could not remove that team member.");
      }
    }
  }

  const pendingInvites = (invites ?? []).filter((i) => i.status === "pending");

  return (
    <AppShell title="Team" eyebrow="Workspace" icon={<UsersIcon size={17} />}>
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}
      {actionError && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {actionError}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3>Members</h3>
        </div>
        {members === null ? (
          <div className="skeleton" style={{ height: 72 }} />
        ) : (
          members.map((m) => (
            <div
              key={m.id}
              style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--ink-100)" }}
            >
              <div>
                <strong style={{ fontSize: 13.5 }}>{m.email}</strong>
                <div className="muted" style={{ fontSize: 12 }}>
                  Joined {new Date(m.created_at).toLocaleDateString()}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="badge neutral">{m.role}</span>
                <button className="btn secondary sm" onClick={() => removeMember(m.id)}>
                  Remove
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {isAdmin && (
        <>
          <div className="card">
            <div className="card-header">
              <h3>Invite a teammate</h3>
            </div>
            <p className="muted" style={{ marginTop: -4 }}>
              There is no email delivery yet — you'll get a link below to copy and send to
              them yourself.
            </p>
            <form onSubmit={sendInvite} style={{ display: "flex", gap: 14, alignItems: "flex-end", flexWrap: "wrap" }}>
              <div style={{ flex: 2, minWidth: 220 }}>
                <label htmlFor="invite-email">Email</label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                />
              </div>
              <div style={{ flex: 1, minWidth: 140 }}>
                <label htmlFor="invite-role">Role</label>
                <select id="invite-role" value={inviteRole} onChange={(e) => setInviteRole(e.target.value as TenantRole)}>
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <button className="btn primary" type="submit" disabled={inviteBusy}>
                {inviteBusy ? <span className="spinner" /> : null} Create invite
              </button>
            </form>
            {inviteError && (
              <div className="error-banner" style={{ marginTop: 10 }}>
                <AlertIcon size={15} />
                {inviteError}
              </div>
            )}
            {lastInvite && (
              <div style={{ marginTop: 14 }}>
                <label htmlFor="invite-link">
                  Invite link for {lastInvite.email} — copy and send it to them
                </label>
                <input id="invite-link" readOnly value={lastInvite.invite_url} onFocus={(e) => e.target.select()} />
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <h3>Pending invites</h3>
            </div>
            {pendingInvites.length === 0 ? (
              <p className="muted">No pending invites.</p>
            ) : (
              pendingInvites.map((i) => (
                <div
                  key={i.id}
                  style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--ink-100)" }}
                >
                  <div>
                    <strong style={{ fontSize: 13.5 }}>{i.email}</strong>
                    <div className="muted" style={{ fontSize: 12 }}>
                      Expires {new Date(i.expires_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="badge neutral">{i.role}</span>
                    <button className="btn secondary sm" onClick={() => revokeInvite(i.id)}>
                      Revoke
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
