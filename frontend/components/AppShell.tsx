"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useParams, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";
import { ShieldIcon, GridIcon, UploadIcon, DocIcon, FileSearchIcon } from "./icons";

interface AppShellProps {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  narrow?: boolean;
  children: ReactNode;
}

export default function AppShell({ title, eyebrow, actions, narrow, children }: AppShellProps) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const params = useParams<{ id?: string }>();
  const engagementId = params?.id;

  function signOut() {
    clearToken();
    router.push("/");
  }

  const base = engagementId ? `/engagements/${engagementId}` : "";

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link href="/engagements" className="sidebar-brand" style={{ textDecoration: "none" }}>
          <div className="sidebar-brand-mark">
            <ShieldIcon size={16} className="mono" />
          </div>
          <div className="sidebar-brand-text">
            Audit Intelligence
            <small>Evidence-grounded</small>
          </div>
        </Link>

        <div className="sidebar-section-label">Workspace</div>
        <Link href="/engagements" className={`sidebar-link ${pathname === "/engagements" ? "active" : ""}`}>
          <GridIcon size={16} /> Engagements
        </Link>

        {engagementId && (
          <>
            <div className="sidebar-section-label">This engagement</div>
            <Link href={base} className={`sidebar-link ${pathname === base ? "active" : ""}`}>
              <ShieldIcon size={16} /> Overview
            </Link>
            <Link
              href={`${base}/upload`}
              className={`sidebar-link ${pathname === `${base}/upload` ? "active" : ""}`}
            >
              <UploadIcon size={16} /> Upload data
            </Link>
            <Link
              href={`${base}/findings`}
              className={`sidebar-link ${pathname.startsWith(`${base}/findings`) ? "active" : ""}`}
            >
              <FileSearchIcon size={16} /> Findings
            </Link>
            <Link
              href={`${base}/reports`}
              className={`sidebar-link ${pathname === `${base}/reports` ? "active" : ""}`}
            >
              <DocIcon size={16} /> Report
            </Link>
          </>
        )}

        <div className="sidebar-footer">
          <button className="sidebar-signout" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div className="app-topbar-title">
            <div>
              {eyebrow && <div className="app-topbar-eyebrow">{eyebrow}</div>}
              <h1 style={{ fontSize: 21, marginBottom: 0 }}>{title}</h1>
            </div>
          </div>
          {actions}
        </header>
        <main className={`app-content ${narrow ? "narrow" : ""}`}>{children}</main>
      </div>
    </div>
  );
}
