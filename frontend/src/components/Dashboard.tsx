"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { clearToken } from "@/lib/auth";
import type { Member, Template, Health, Approval } from "@/lib/types";
import Toast from "./Toast";
import SendTab from "./tabs/SendTab";
import ApprovalsTab from "./tabs/ApprovalsTab";
import TemplatesTab from "./tabs/TemplatesTab";
import MembersTab from "./tabs/MembersTab";
import HistoryTab from "./tabs/HistoryTab";
import JobsTab from "./tabs/JobsTab";

type Tab = "send" | "approvals" | "templates" | "members" | "history" | "jobs";

type Props = { onLogout: () => void };

export default function Dashboard({ onLogout }: Props) {
  const [tab, setTab] = useState<Tab>("send");
  const [nftTypes, setNftTypes] = useState<string[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [approvalCount, setApprovalCount] = useState(0);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  function notify(msg: string, err = false) {
    setToast({ msg, type: err ? "error" : "success" });
  }

  async function loadAll() {
    try {
      const [nfts, mems, tmpls, h] = await Promise.all([
        api.nftTypes(),
        api.members.list(),
        api.templates.list(),
        api.health(),
      ]);
      setNftTypes(nfts);
      setMembers(mems);
      setTemplates(tmpls);
      setHealth(h);
    } catch (e: any) {
      notify(e.message, true);
    }
  }

  async function loadApprovalCount() {
    try {
      const list = await api.approvals.list();
      setApprovalCount(list.length);
    } catch {}
  }

  useEffect(() => {
    loadAll();
    loadApprovalCount();
    const handler = () => { clearToken(); onLogout(); };
    window.addEventListener("betimail:unauthorized", handler);
    const interval = setInterval(loadApprovalCount, 10000);
    return () => {
      window.removeEventListener("betimail:unauthorized", handler);
      clearInterval(interval);
    };
  }, []);

  function logout() {
    clearToken();
    onLogout();
  }

  const tabs: { key: Tab; label: string; badge?: number }[] = [
    { key: "send", label: "📤 メール送信" },
    { key: "approvals", label: "⏳ 承認待ち", badge: approvalCount },
    { key: "templates", label: "📝 テンプレート" },
    { key: "members", label: "👥 メンバー管理" },
    { key: "history", label: "📋 送受信履歴" },
    { key: "jobs", label: "🚚 送信ジョブ" },
  ];

  return (
    <>
      <header className="app-header">
        <h1>⚡ Betimail</h1>
        <span className="sub">NFTコミュニティ サポートメール管理</span>
        <div className="right">
          {health && (
            <>
              <span>
                <span className="badge-dot" style={{ background: health.admin_auth_enabled ? "#4caf50" : "#ff9800" }}></span>
                {health.admin_auth_enabled ? "認証ON" : "認証OFF (要設定)"}
              </span>
              <span>
                <span className="badge-dot" style={{ background: health.telegram_enabled ? "#4caf50" : "#888" }}></span>
                Telegram {health.telegram_enabled ? "有効" : "無効"}
              </span>
            </>
          )}
          <button className="logout" onClick={logout}>ログアウト</button>
        </div>
      </header>

      <nav className="app-nav">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? "active" : ""}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {t.badge != null && t.badge > 0 && <span className="count">{t.badge}</span>}
          </button>
        ))}
      </nav>

      <main className="app-main">
        {tab === "send" && (
          <SendTab
            nftTypes={nftTypes}
            members={members}
            templates={templates}
            onReload={loadAll}
            notify={notify}
            onJump={(t) => setTab(t as Tab)}
          />
        )}
        {tab === "approvals" && <ApprovalsTab notify={notify} onChange={loadApprovalCount} />}
        {tab === "templates" && <TemplatesTab templates={templates} notify={notify} onReload={loadAll} />}
        {tab === "members" && <MembersTab nftTypes={nftTypes} members={members} notify={notify} onReload={loadAll} />}
        {tab === "history" && <HistoryTab notify={notify} />}
        {tab === "jobs" && <JobsTab notify={notify} />}
      </main>

      {toast && <Toast message={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
    </>
  );
}
