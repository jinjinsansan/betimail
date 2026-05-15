"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Member, SentEmail, ReceivedEmail, BulkJob, Approval, WithdrawStats } from "@/lib/types";
import { NFT_TYPES, nftBadgeClass, nftLabel, statusInfo, fmtDate } from "@/lib/ui";
import { I } from "@/lib/icons";
import { StatCard, Empty, ConfBar } from "../common";
import type { TabKey } from "../Sidebar";

type Props = {
  members: Member[];
  approvals: Approval[];
  sent: SentEmail[];
  received: ReceivedEmail[];
  jobs: BulkJob[];
  onNavigate: (key: TabKey) => void;
};

export default function DashboardTab({ members, approvals, sent, received, jobs, onNavigate }: Props) {
  const [withdrawStats, setWithdrawStats] = useState<WithdrawStats | null>(null);
  useEffect(() => { api.withdraws.stats().then(setWithdrawStats).catch(() => {}); }, []);

  const stats = useMemo(() => {
    const last7 = new Date();
    last7.setDate(last7.getDate() - 7);
    const sent7 = sent.filter((s) => new Date(s.sent_at) >= last7).length;
    const recv7 = received.filter((r) => new Date(r.received_at) >= last7).length;
    const sentOK = sent.filter((s) => s.status === "sent").length;
    const sentRate = sent.length ? Math.round((sentOK / sent.length) * 100) : 100;
    const autoSent7 = received.filter((r) => r.status === "auto_sent" && new Date(r.received_at) >= last7).length;
    return { sent7, recv7, sentRate, autoSent7 };
  }, [sent, received]);

  const nftCounts = useMemo(() => {
    const c: Record<string, number> = {};
    NFT_TYPES.forEach((t) => (c[t] = 0));
    members.forEach((m) => {
      (m.nft_type || "")
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
        .forEach((t) => {
          if (c[t] != null) c[t]++;
        });
    });
    return c;
  }, [members]);

  const series = useMemo(() => {
    const days = 14;
    const sentBuckets = new Array(days).fill(0);
    const recvBuckets = new Array(days).fill(0);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const start = new Date(today);
    start.setDate(start.getDate() - (days - 1));
    sent.forEach((s) => {
      const d = new Date(s.sent_at);
      d.setHours(0, 0, 0, 0);
      const diff = Math.floor((d.getTime() - start.getTime()) / 86400000);
      if (diff >= 0 && diff < days) sentBuckets[diff]++;
    });
    received.forEach((r) => {
      const d = new Date(r.received_at);
      d.setHours(0, 0, 0, 0);
      const diff = Math.floor((d.getTime() - start.getTime()) / 86400000);
      if (diff >= 0 && diff < days) recvBuckets[diff]++;
    });
    return { sentBuckets, recvBuckets };
  }, [sent, received]);

  const recentJobs = jobs.slice(0, 3);
  const recentApprovals = approvals.slice(0, 3);

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">ダッシュボード</h1>
          <div className="page-sub">
            {new Date().toLocaleDateString("ja-JP", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}{" "}
            ・ 直近の状況をお伝えします。
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn ghost" onClick={() => onNavigate("history")}><I.Activity /> 履歴を見る</button>
          <button className="btn primary" onClick={() => onNavigate("send")}><I.Send /> 新規メール送信</button>
        </div>
      </div>

      <div className="stat-grid">
        <StatCard label="メンバー総数" value={members.length} delta={`${NFT_TYPES.length} 種別`} icon={<I.Users />} />
        <StatCard label="今週の送信" value={stats.sent7} delta={`成功率 ${stats.sentRate}%`} deltaUp={stats.sentRate >= 95} icon={<I.Send />} />
        <StatCard label="今週の受信" value={stats.recv7} delta={stats.autoSent7 > 0 ? `AI自動返信 ${stats.autoSent7}件` : "AI自動返信 0件"} icon={<I.Inbox />} />
        <StatCard
          label="承認待ち"
          value={approvals.length}
          delta={approvals.length > 0 ? "確認してください" : "問題なし"}
          deltaDown={approvals.length > 2}
          icon={<I.Clock />}
          danger={approvals.length > 2}
          onClick={() => onNavigate("approvals")}
        />
      </div>

      <div className="stat-grid" style={{ marginTop: 12 }}>
        <StatCard
          label="買い取り支払い累計"
          value={withdrawStats ? `$${withdrawStats.total_usdt.toLocaleString()}` : "—"}
          delta={withdrawStats ? `${withdrawStats.count}件 / ${withdrawStats.unique_recipients}名` : ""}
          icon={<I.DollarSign />}
          onClick={() => onNavigate("withdraws")}
        />
        <StatCard
          label="送信ジョブ"
          value={jobs.length}
          delta={`実行中 ${jobs.filter((j) => j.status === "running").length} / 完了 ${jobs.filter((j) => j.status === "done").length}`}
          icon={<I.Truck />}
          onClick={() => onNavigate("jobs")}
        />
        <StatCard
          label="テンプレート"
          value={"—"}
          delta="管理画面で確認"
          icon={<I.FileText />}
          onClick={() => onNavigate("templates")}
        />
        <StatCard
          label="メールスループット"
          value={sent.length + received.length}
          delta={`累計 送信${sent.length} / 受信${received.length}`}
          icon={<I.Activity />}
          onClick={() => onNavigate("history")}
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20, marginTop: 20 }}>
        <div className="card">
          <div className="card-head">
            <h3>送受信トレンド</h3>
            <span className="badge badge-neutral">過去14日</span>
            <div className="card-head-actions">
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-3)" }}>
                <span style={{ width: 8, height: 8, background: "var(--accent)", borderRadius: 2 }} /> 送信
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-3)", marginLeft: 12 }}>
                <span style={{ width: 8, height: 8, background: "var(--info)", borderRadius: 2 }} /> 受信
              </span>
            </div>
          </div>
          <div className="card-body">
            <BarChart sent={series.sentBuckets} received={series.recvBuckets} />
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>メンバー内訳</h3>
            <span className="badge badge-neutral">{members.length} 名</span>
          </div>
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {NFT_TYPES.map((t) => {
              const pct = members.length ? Math.round((nftCounts[t] / members.length) * 100) : 0;
              return (
                <div key={t}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                    <span className={`badge ${nftBadgeClass(t)} dot`}>{nftLabel(t)}</span>
                    <span style={{ fontSize: 13, color: "var(--text-2)", fontVariantNumeric: "tabular-nums" }}>
                      {nftCounts[t]} <span style={{ color: "var(--text-4)" }}>· {pct}%</span>
                    </span>
                  </div>
                  <div className="progress"><div style={{ width: pct + "%" }} /></div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 20 }}>
        <div className="card">
          <div className="card-head">
            <h3>承認待ちの返信</h3>
            <span className="badge badge-warning">{approvals.length}</span>
            <div className="card-head-actions">
              <button className="btn ghost sm" onClick={() => onNavigate("approvals")}>すべて表示 <I.ArrowRight /></button>
            </div>
          </div>
          <div className="card-body flush">
            {recentApprovals.length === 0 ? (
              <Empty icon={<I.Check />} title="承認待ちはありません" sub="AIが自動応答を完了しています。" />
            ) : recentApprovals.map((a) => (
              <div
                key={a.id}
                style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", cursor: "pointer" }}
                onClick={() => onNavigate("approvals")}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                  <b style={{ fontSize: 13.5 }}>{a.sender_name || a.sender_email}</b>
                  <span style={{ fontSize: 12, color: "var(--text-3)" }}>{a.sender_email}</span>
                  <span style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--text-4)" }}>{fmtDate(a.created_at)}</span>
                </div>
                <div style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 6 }}>{a.original_subject || "(件名なし)"}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>最近の送信ジョブ</h3>
            <div className="card-head-actions">
              <button className="btn ghost sm" onClick={() => onNavigate("jobs")}>すべて表示 <I.ArrowRight /></button>
            </div>
          </div>
          <div className="card-body flush">
            {recentJobs.length === 0 ? (
              <Empty icon={<I.Truck />} title="ジョブはまだありません" sub="メール送信を実行するとここに表示されます。" />
            ) : recentJobs.map((j) => {
              const done = j.sent + j.failed;
              const pct = j.total ? Math.round((done / j.total) * 100) : 0;
              const s = statusInfo(j.status);
              return (
                <div key={j.id} style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-4)" }}>#{j.id}</span>
                    <b style={{ fontSize: 13.5, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{j.subject}</b>
                    <span className={`badge ${s.cls}`}>{s.label}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 12, color: "var(--text-3)" }}>
                    <span>{done} / {j.total} 配信</span>
                    {j.failed > 0 && <span style={{ color: "var(--danger)" }}>失敗 {j.failed}</span>}
                    <span style={{ marginLeft: "auto" }}>{fmtDate(j.created_at)}</span>
                  </div>
                  <div className="progress" style={{ marginTop: 6 }}><div style={{ width: pct + "%" }} /></div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}

function BarChart({ sent, received }: { sent: number[]; received: number[] }) {
  const max = Math.max(1, ...sent, ...received);
  const days = sent.length;
  const today = new Date();
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 160 }}>
      {sent.map((v, i) => {
        const r = received[i];
        const d = new Date(today);
        d.setDate(today.getDate() - (days - 1 - i));
        const dayLbl = `${d.getMonth() + 1}/${d.getDate()}`;
        return (
          <div
            key={i}
            style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: "100%" }}
            title={`${dayLbl} 送信 ${v} / 受信 ${r}`}
          >
            <div style={{ flex: 1, display: "flex", alignItems: "flex-end", gap: 2, width: "100%", justifyContent: "center" }}>
              <div style={{ width: "40%", height: `${(v / max) * 100}%`, background: "var(--accent)", borderRadius: 2, minHeight: v ? 2 : 0 }} />
              <div style={{ width: "40%", height: `${(r / max) * 100}%`, background: "var(--info)", borderRadius: 2, minHeight: r ? 2 : 0, opacity: 0.8 }} />
            </div>
            <div style={{ fontSize: 10, color: "var(--text-4)", fontVariantNumeric: "tabular-nums" }}>{dayLbl}</div>
          </div>
        );
      })}
    </div>
  );
}
