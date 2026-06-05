"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { clearToken } from "@/lib/auth";
import type { Member, Template, Health, Approval, SentEmail, ReceivedEmail, BulkJob } from "@/lib/types";
import Sidebar, { TabKey } from "./Sidebar";
import Topbar from "./Topbar";
import { ToastStack, useToasts } from "./common";
import DashboardTab from "./tabs/DashboardTab";
import SendTab from "./tabs/SendTab";
import ApprovalsTab from "./tabs/ApprovalsTab";
import TemplatesTab from "./tabs/TemplatesTab";
import MembersTab from "./tabs/MembersTab";
import HistoryTab from "./tabs/HistoryTab";
import JobsTab from "./tabs/JobsTab";
import WithdrawsTab from "./tabs/WithdrawsTab";
import AfiWithdrawsTab from "./tabs/AfiWithdrawsTab";

type Props = { onLogout: () => void };

export default function Dashboard({ onLogout }: Props) {
  const [tab, setTab] = useState<TabKey>("dashboard");
  const [members, setMembers] = useState<Member[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [sentEmails, setSentEmails] = useState<SentEmail[]>([]);
  const [recvEmails, setRecvEmails] = useState<ReceivedEmail[]>([]);
  const [jobs, setJobs] = useState<BulkJob[]>([]);
  const [username, setUsername] = useState("admin");
  const { toasts, notify, dismiss } = useToasts();

  // ログイン中のユーザー名を取得
  useEffect(() => {
    api.check().then((r) => setUsername(r.username || "admin")).catch(() => {});
  }, []);

  async function loadAll() {
    try {
      const [mems, tmpls, h] = await Promise.all([
        api.members.list(),
        api.templates.list(),
        api.health(),
      ]);
      setMembers(mems);
      setTemplates(tmpls);
      setHealth(h);
    } catch (e: any) {
      notify(e.message, "error");
    }
  }

  async function loadDashboardData() {
    try {
      const [aps, s, r, j] = await Promise.all([
        api.approvals.list(),
        api.emails.sent(100, 0, ""),
        api.emails.received(100, 0, ""),
        api.send.jobs(),
      ]);
      setApprovals(aps);
      setSentEmails(s.items);
      setRecvEmails(r.items);
      setJobs(j);
    } catch (e: any) {
      notify(e.message, "error");
    }
  }

  async function loadApprovalCount() {
    try {
      const list = await api.approvals.list();
      setApprovals(list);
    } catch {}
  }

  useEffect(() => {
    loadAll();
    loadDashboardData();
    const handler = () => { clearToken(); onLogout(); };
    window.addEventListener("betimail:unauthorized", handler);
    const interval = setInterval(loadApprovalCount, 10000);
    return () => {
      window.removeEventListener("betimail:unauthorized", handler);
      clearInterval(interval);
    };
  }, []);

  // ダッシュボードに切り替えるたびに最新化
  useEffect(() => {
    if (tab === "dashboard") loadDashboardData();
  }, [tab]);

  function logout() {
    clearToken();
    onLogout();
  }

  const trails: Record<TabKey, string[]> = {
    dashboard: ["Betimail", "ダッシュボード"],
    send: ["Betimail", "メール", "メール送信"],
    approvals: ["Betimail", "メール", "承認待ち"],
    members: ["Betimail", "メール", "メンバー管理"],
    history: ["Betimail", "メール", "送受信履歴"],
    withdraws: ["Betimail", "買い取り", "出金履歴"],
    "afi-withdraws": ["Betimail", "買い取り", "アフィリエイト出金 (afi.irah.uk)"],
    templates: ["Betimail", "設定", "テンプレート"],
    jobs: ["Betimail", "設定", "送信ジョブ"],
  };

  return (
    <>
      <div className="shell">
        <Sidebar
          current={tab}
          onNavigate={setTab}
          approvalCount={approvals.length}
          health={health}
          username={username}
          onLogout={logout}
        />
        <div className="main">
          <Topbar trail={trails[tab]} />
          <div className="content">
            {tab === "dashboard" && (
              <DashboardTab
                members={members}
                approvals={approvals}
                sent={sentEmails}
                received={recvEmails}
                jobs={jobs}
                onNavigate={setTab}
              />
            )}
            {tab === "send" && (
              <SendTab
                members={members}
                templates={templates}
                onReload={() => { loadAll(); loadDashboardData(); }}
                notify={notify}
              />
            )}
            {tab === "approvals" && <ApprovalsTab notify={notify} onChange={loadApprovalCount} />}
            {tab === "templates" && <TemplatesTab templates={templates} notify={notify} onReload={loadAll} />}
            {tab === "members" && <MembersTab members={members} notify={notify} onReload={loadAll} />}
            {tab === "history" && <HistoryTab notify={notify} />}
            {tab === "withdraws" && <WithdrawsTab notify={notify} />}
            {tab === "afi-withdraws" && <AfiWithdrawsTab notify={notify} />}
            {tab === "jobs" && <JobsTab notify={notify} />}
          </div>
        </div>
      </div>
      <ToastStack toasts={toasts} dismiss={dismiss} />
    </>
  );
}
