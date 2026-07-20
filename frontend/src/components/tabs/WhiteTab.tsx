"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { WhiteTotals, WhiteWithdrawal, WhiteMemberRow, WhiteMemberDetail } from "@/lib/types";
import { fmtDate } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Empty } from "../common";

type Props = {
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

const WD_STATUSES = ["pending", "processing", "paid", "rejected"];
const WD_LABELS: Record<string, string> = {
  pending: "申請中", processing: "処理中", paid: "支払完了", rejected: "却下", cancelled: "取り下げ",
};

function statusBadgeClass(status: string): string {
  if (status === "paid") return "badge-success";
  if (status === "rejected" || status === "cancelled") return "badge-neutral";
  if (status === "processing") return "badge-info";
  return "badge-warning";
}

export default function WhiteTab({ notify }: Props) {
  const [totals, setTotals] = useState<WhiteTotals | null>(null);
  const [withdrawals, setWithdrawals] = useState<WhiteWithdrawal[]>([]);
  const [loading, setLoading] = useState(false);
  const [wdFilter, setWdFilter] = useState("");

  async function reload() {
    setLoading(true);
    try {
      const [s, w] = await Promise.all([api.white.summary(), api.white.withdrawals(wdFilter)]);
      setTotals(s.totals);
      setWithdrawals(w.withdrawals);
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload(); }, [wdFilter]);

  const pendingWd = totals?.withdrawals_by_status?.pending;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">白のダッシュボード管理（旧 afi.irah.uk）</h1>
          <div className="page-sub">
            会員資産（会員権・ホイホイ・afi残高）の照会と出金申請の処理。送金はポータル側を優先する運用です
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn ghost" onClick={reload} disabled={loading}>
            <I.Refresh /> 更新
          </button>
        </div>
      </div>

      {totals && (
        <div className="stat-grid">
          <div className="stat">
            <div className="stat-label">会員数</div>
            <div className="stat-value">{totals.members.toLocaleString()}</div>
            <div className="stat-delta">名（残高ありは {totals.members_with_balance} 名）</div>
          </div>
          <div className="stat">
            <div className="stat-label">残高合計</div>
            <div className="stat-value">${totals.total_balance.toLocaleString("ja-JP", { maximumFractionDigits: 2 })}</div>
            <div className="stat-delta">USDT（凍結スナップショット）</div>
          </div>
          <div className="stat">
            <div className="stat-label">会員権 / ホイホイ</div>
            <div className="stat-value">{totals.total_kaiin_units.toLocaleString()} / {totals.total_hoihoi_units.toLocaleString()}</div>
            <div className="stat-delta">口（afi 表示値）</div>
          </div>
          <div className="stat">
            <div className="stat-label">出金申請</div>
            <div className="stat-value">{pendingWd?.count || 0}</div>
            <div className="stat-delta">件が対応待ち（${(pendingWd?.amount || 0).toLocaleString("ja-JP", { maximumFractionDigits: 2 })}）</div>
          </div>
        </div>
      )}

      <WithdrawalsCard
        withdrawals={withdrawals} filter={wdFilter} setFilter={setWdFilter}
        notify={notify} onChange={reload}
      />

      <MemberSearchCard notify={notify} />
    </>
  );
}

function WithdrawalsCard({ withdrawals, filter, setFilter, notify, onChange }: {
  withdrawals: WhiteWithdrawal[]; filter: string; setFilter: (s: string) => void;
  notify: Props["notify"]; onChange: () => void;
}) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [paidConfirm, setPaidConfirm] = useState<WhiteWithdrawal | null>(null);

  async function updateStatus(w: WhiteWithdrawal, status: string) {
    if (status === w.status) return;
    if (status === "paid") { setPaidConfirm(w); return; }
    await applyStatus(w, status);
  }

  async function applyStatus(w: WhiteWithdrawal, status: string) {
    setBusyId(w.id);
    try {
      await api.white.updateWithdrawal(w.id, status);
      notify(`出金申請 #${w.id} を「${WD_LABELS[status] || status}」に更新しました`, "success");
      setPaidConfirm(null);
      onChange();
    } catch (e: any) {
      notify(e.message || "更新に失敗しました", "error");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="card-head">
        <h3>出金申請（白のダッシュボード残高）</h3>
        <select className="input" style={{ width: 140, padding: "6px 10px" }} value={filter}
          onChange={(e) => setFilter(e.target.value)}>
          <option value="">すべて</option>
          {[...WD_STATUSES, "cancelled"].map((s) => <option key={s} value={s}>{WD_LABELS[s]}</option>)}
        </select>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 55 }}>ID</th>
              <th>会員</th>
              <th style={{ width: 110 }}>金額</th>
              <th>送金先</th>
              <th style={{ width: 140 }}>申請日時</th>
              <th style={{ width: 100 }}>状態</th>
              <th style={{ width: 140 }}>状態を変更</th>
            </tr>
          </thead>
          <tbody>
            {withdrawals.length === 0 ? (
              <tr><td colSpan={7}><Empty icon={<I.Inbox />} title="出金申請はまだありません" /></td></tr>
            ) : withdrawals.map((w) => (
              <tr key={w.id}>
                <td style={{ fontVariantNumeric: "tabular-nums" }}>#{w.id}</td>
                <td>
                  <div style={{ fontWeight: 600 }}>{w.name || "—"}</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{w.email}</div>
                </td>
                <td style={{ fontVariantNumeric: "tabular-nums" }}><b>${w.amount.toLocaleString("ja-JP", { minimumFractionDigits: 2 })}</b></td>
                <td>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--text-3)", wordBreak: "break-all" }}>
                    {w.destination}
                  </span>
                </td>
                <td><span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtDate(w.requested_at)}</span></td>
                <td><span className={`badge ${statusBadgeClass(w.status)}`}>{WD_LABELS[w.status] || w.status}</span></td>
                <td>
                  {["paid", "cancelled"].includes(w.status) ? (
                    <span style={{ fontSize: 12, color: "var(--text-3)" }}>変更不可</span>
                  ) : (
                    <select className="input" style={{ width: "100%", padding: "6px 8px" }}
                      value={w.status} disabled={busyId === w.id}
                      onChange={(e) => updateStatus(w, e.target.value)}>
                      {WD_STATUSES.map((s) => <option key={s} value={s}>{WD_LABELS[s]}</option>)}
                    </select>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {paidConfirm && (
        <div className="card-body" style={{ borderTop: "1px solid var(--border)", background: "#fff7ed" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#9a3412", marginBottom: 6 }}>
            ⚠️ 出金申請 #{paidConfirm.id} を「支払完了」にしますか？
          </div>
          <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 10, lineHeight: 1.7 }}>
            {paidConfirm.name || paidConfirm.email} さんの白ダッシュボード残高から <b>${paidConfirm.amount.toLocaleString("ja-JP", { minimumFractionDigits: 2 })} USDT</b> が差し引かれます。
            実際の送金が完了していることを確認してから実行してください。
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn danger" onClick={() => applyStatus(paidConfirm, "paid")} disabled={busyId === paidConfirm.id}>
              {busyId === paidConfirm.id ? "処理中…" : "支払完了にする（残高減算）"}
            </button>
            <button className="btn ghost" onClick={() => setPaidConfirm(null)} disabled={busyId === paidConfirm.id}>
              キャンセル
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function MemberSearchCard({ notify }: { notify: Props["notify"] }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<WhiteMemberRow[]>([]);
  const [detail, setDetail] = useState<WhiteMemberDetail | null>(null);
  const [busy, setBusy] = useState(false);

  async function search() {
    setBusy(true); setDetail(null);
    try {
      const r = await api.white.members(q);
      setRows(r.members);
      if (r.members.length === 0) notify("該当する会員が見つかりません", "info");
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function openDetail(email: string) {
    setBusy(true);
    try {
      setDetail(await api.white.memberDetail(email));
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="card-head"><h3>白ダッシュボード会員検索</h3></div>
      <div className="card-body">
        <div style={{ display: "flex", gap: 8 }}>
          <input className="input" type="text" placeholder="メールアドレス または 名前で検索"
            value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") search(); }}
            style={{ flex: 1 }} />
          <button className="btn primary" onClick={search} disabled={busy}>
            <I.Search /> 検索
          </button>
        </div>

        {rows.length > 0 && !detail && (
          <div className="tbl-wrap" style={{ marginTop: 14 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>会員</th>
                  <th style={{ width: 120 }}>残高</th>
                  <th style={{ width: 100 }}>会員権</th>
                  <th style={{ width: 100 }}>ホイホイ</th>
                  <th style={{ width: 90 }}></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => (
                  <tr key={m.email}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{m.name || "—"}{m.source === "preview" && <span className="badge badge-neutral" style={{ marginLeft: 6 }}>preview</span>}</div>
                      <div style={{ fontSize: 12, color: "var(--text-3)" }}>{m.email}</div>
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>${m.balance.toLocaleString("ja-JP", { minimumFractionDigits: 2 })}</td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{m.kaiin_units}口</td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{m.hoihoi_units}口</td>
                    <td><button className="btn ghost" onClick={() => openDetail(m.email)} disabled={busy}>詳細</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {detail && (
          <div style={{ marginTop: 14, padding: 14, background: "var(--bg-inset)", borderRadius: 10, border: "1px solid var(--border)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{detail.name || "—"}</div>
                <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>{detail.email}</div>
                {detail.wallet_address && (
                  <div style={{ fontSize: 11.5, color: "var(--text-3)", fontFamily: "var(--font-mono)", marginTop: 4, wordBreak: "break-all" }}>
                    💳 {detail.wallet_address}
                  </div>
                )}
              </div>
              <button className="btn ghost" onClick={() => setDetail(null)}>閉じる</button>
            </div>
            <div style={{ display: "flex", gap: 18, marginTop: 12, flexWrap: "wrap", fontSize: 13 }}>
              <span>残高 <b style={{ fontVariantNumeric: "tabular-nums" }}>${detail.balance.toLocaleString("ja-JP", { minimumFractionDigits: 2 })}</b></span>
              <span>会員権 <b>{detail.kaiin_units}</b> 口</span>
              <span>ホイホイ <b>{detail.hoihoi_units}</b> 口</span>
              <span>出金申請 <b>{detail.withdrawals.length + detail.legacy_withdrawals.length}</b> 件</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
