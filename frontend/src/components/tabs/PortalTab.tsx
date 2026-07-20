"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type {
  PortalAdminSummary, PortalBuyback, PortalWithdrawal, PortalMemberRow, PortalMemberDetail,
} from "@/lib/types";
import { fmtDate } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Empty } from "../common";

type Props = {
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

const NFT_LABELS: Record<string, string> = {
  MEMBER: "会員権NFT",
  HOIHOI: "パチスロホイホイNFT",
  SPECIAL_MUSTARD: "スペシャルマスタード",
  LEADER: "LEADER",
  DIGITAL_PACHISURO: "DIGITAL_PACHISURO",
};

const BUYBACK_STATUSES = ["pending", "confirmed", "processing", "paid", "rejected"];
const BUYBACK_LABELS: Record<string, string> = {
  pending: "申請受付", confirmed: "確認済み", processing: "処理中", paid: "支払完了", rejected: "却下",
};
const WD_STATUSES = ["pending", "processing", "paid", "rejected"];
const WD_LABELS: Record<string, string> = {
  pending: "申請中", processing: "処理中", paid: "支払完了", rejected: "却下", cancelled: "取り下げ",
};

function statusBadgeClass(status: string): string {
  if (status === "paid") return "badge-success";
  if (status === "rejected" || status === "cancelled") return "badge-neutral";
  if (status === "processing" || status === "confirmed") return "badge-info";
  return "badge-warning";
}

export default function PortalTab({ notify }: Props) {
  const [summary, setSummary] = useState<PortalAdminSummary | null>(null);
  const [buybacks, setBuybacks] = useState<PortalBuyback[]>([]);
  const [withdrawals, setWithdrawals] = useState<PortalWithdrawal[]>([]);
  const [loading, setLoading] = useState(false);
  const [bbFilter, setBbFilter] = useState("");
  const [wdFilter, setWdFilter] = useState("");

  async function reload() {
    setLoading(true);
    try {
      const [s, b, w] = await Promise.all([
        api.portal.summary(),
        api.portal.buybacks(bbFilter),
        api.portal.withdrawals(wdFilter),
      ]);
      setSummary(s);
      setBuybacks(b.buybacks);
      setWithdrawals(w.withdrawals);
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload(); }, [bbFilter, wdFilter]);

  const totals = summary?.totals;
  const pendingBb = totals?.buybacks_by_status?.pending || 0;
  const pendingWd = totals?.withdrawals_by_status?.pending?.count || 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">ポータル管理（betiダッシュボード）</h1>
          <div className="page-sub">
            会員資産・買い取り原資の分配・買い取り申請・出金申請を管理します
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
            <div className="stat-label">ポータル会員</div>
            <div className="stat-value">{totals.members.toLocaleString()}</div>
            <div className="stat-delta">名（移行済み）</div>
          </div>
          <div className="stat">
            <div className="stat-label">会員残高合計</div>
            <div className="stat-value">${totals.total_balance.toLocaleString("ja-JP", { maximumFractionDigits: 2 })}</div>
            <div className="stat-delta">USDT</div>
          </div>
          <div className="stat">
            <div className="stat-label">買い取り申請</div>
            <div className="stat-value">{pendingBb}</div>
            <div className="stat-delta">件が対応待ち</div>
          </div>
          <div className="stat">
            <div className="stat-label">出金申請</div>
            <div className="stat-value">{pendingWd}</div>
            <div className="stat-delta">件が対応待ち</div>
          </div>
        </div>
      )}

      {totals && totals.assets.length > 0 && (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-head"><h3>NFT別資産</h3></div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>NFT種別</th>
                  <th style={{ width: 110 }}>保有者数</th>
                  <th style={{ width: 130 }}>購入口数</th>
                  <th style={{ width: 170 }}>ステーク口数（分配母数）</th>
                </tr>
              </thead>
              <tbody>
                {totals.assets.map((a) => (
                  <tr key={a.nft_type}>
                    <td><b>{NFT_LABELS[a.nft_type] || a.nft_type}</b></td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{a.holders.toLocaleString()}</td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{a.purchased_units.toLocaleString()}</td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}><b>{a.staked_units.toLocaleString()}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 20, marginTop: 20 }}>
        <DistributePanel notify={notify} onDone={reload} summary={summary} />
        <DistributionHistory summary={summary} />
      </div>

      <BuybacksCard
        buybacks={buybacks} filter={bbFilter} setFilter={setBbFilter}
        notify={notify} onChange={reload}
      />

      <WithdrawalsCard
        withdrawals={withdrawals} filter={wdFilter} setFilter={setWdFilter}
        notify={notify} onChange={reload}
      />

      <MemberSearchCard notify={notify} />
    </>
  );
}

/* ---------- 分配パネル ---------- */

function DistributePanel({ notify, onDone, summary }: {
  notify: Props["notify"]; onDone: () => void; summary: PortalAdminSummary | null;
}) {
  const [nft, setNft] = useState<"MEMBER" | "HOIHOI">("HOIHOI");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [forceNeeded, setForceNeeded] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const amountNum = parseFloat(amount) || 0;
  const asset = summary?.totals.assets.find((a) => a.nft_type === nft);
  const totalUnits = asset?.staked_units || 0;
  const rate = totalUnits > 0 ? amountNum / totalUnits : 0;

  function reset() { setConfirming(false); setForceNeeded(false); }

  async function doDistribute(force: boolean) {
    if (amountNum <= 0) { notify("金額を入力してください", "error"); return; }
    setSubmitting(true);
    try {
      const r = await api.portal.distribute(nft, amountNum, note, force);
      notify(
        `${NFT_LABELS[nft]}へ分配しました: ${r.recipients}名 / ${r.total_units.toLocaleString()}口 / 計$${r.distributed_total.toLocaleString()} USDT`,
        "success"
      );
      setAmount(""); setNote(""); reset();
      onDone();
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 409) {
        setForceNeeded(true);
        notify(e.message, "info");
      } else {
        notify(e.message || "分配に失敗しました", "error");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card">
      <div className="card-head"><h3>買い取り原資を分配</h3></div>
      <div className="card-body">
        <label style={lbl}>分配先</label>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {(["HOIHOI", "MEMBER"] as const).map((t) => (
            <button key={t}
              className={`btn ${nft === t ? "primary" : "ghost"}`}
              style={{ flex: 1 }}
              onClick={() => { setNft(t); reset(); }}>
              {t === "HOIHOI" ? "パチスロホイホイへ" : "会員権NFTへ"}
            </button>
          ))}
        </div>

        <label style={lbl}>分配総額（USDT）</label>
        <input className="input" type="number" min={1} value={amount}
          onChange={(e) => { setAmount(e.target.value); reset(); }} style={{ width: "100%" }} />

        <label style={{ ...lbl, marginTop: 12 }}>メモ（任意）</label>
        <input className="input" type="text" value={note} placeholder="例: 7月分 買い取り原資"
          onChange={(e) => setNote(e.target.value)} style={{ width: "100%" }} />

        <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 10, lineHeight: 1.7 }}>
          対象 <b>{asset?.holders ?? "—"}</b> 名 / ステーク <b>{totalUnits.toLocaleString()}</b> 口<br />
          1口あたり <b>${rate ? rate.toFixed(6) : "—"}</b>
        </div>

        {!confirming && !forceNeeded && (
          <button className="btn primary" style={{ width: "100%", marginTop: 14 }}
            onClick={() => setConfirming(true)}
            disabled={amountNum <= 0 || totalUnits <= 0}>
            <I.DollarSign /> 分配を実行する
          </button>
        )}

        {confirming && !forceNeeded && (
          <div style={{ marginTop: 14, padding: 12, background: "var(--bg-inset)", borderRadius: 8, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
              {NFT_LABELS[nft]}の保有者へ分配しますか？
            </div>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 10 }}>
              {asset?.holders}名へ合計 約${(rate * totalUnits).toFixed(2)} USDT を残高に加算します。この操作は取り消せません。
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn primary" onClick={() => doDistribute(false)} disabled={submitting}>
                {submitting ? "実行中…" : "確定して分配"}
              </button>
              <button className="btn ghost" onClick={() => setConfirming(false)} disabled={submitting}>
                キャンセル
              </button>
            </div>
          </div>
        )}

        {forceNeeded && (
          <div style={{ marginTop: 14, padding: 12, background: "#fff7ed", borderRadius: 8, border: "1px solid #fed7aa" }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: "#9a3412" }}>
              ⚠️ 本日は既に{NFT_LABELS[nft]}へ分配済みです
            </div>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 10 }}>
              もう一度分配すると会員残高に二重で加算されます。それでも実行しますか？
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn danger" onClick={() => doDistribute(true)} disabled={submitting}>
                {submitting ? "実行中…" : "二重分配を承知で実行"}
              </button>
              <button className="btn ghost" onClick={() => setForceNeeded(false)} disabled={submitting}>
                やめる
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const lbl: React.CSSProperties = {
  display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-3)", marginBottom: 6,
};

function DistributionHistory({ summary }: { summary: PortalAdminSummary | null }) {
  const dists = summary?.distributions || [];
  return (
    <div className="card">
      <div className="card-head">
        <h3>分配履歴</h3>
        <span className="badge badge-neutral">{dists.length}</span>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 140 }}>実行日時</th>
              <th style={{ width: 130 }}>分配先</th>
              <th style={{ width: 100 }}>総額</th>
              <th style={{ width: 90 }}>口数</th>
              <th style={{ width: 100 }}>1口あたり</th>
              <th style={{ width: 70 }}>受取</th>
              <th>メモ</th>
            </tr>
          </thead>
          <tbody>
            {dists.length === 0 ? (
              <tr><td colSpan={7}><Empty icon={<I.Inbox />} title="分配履歴がありません" /></td></tr>
            ) : dists.map((d) => (
              <tr key={d.id}>
                <td><span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtDate(d.created_at)}</span></td>
                <td>{NFT_LABELS[d.nft_type] || d.nft_type}</td>
                <td style={{ fontVariantNumeric: "tabular-nums" }}><b>${d.total_amount.toLocaleString()}</b></td>
                <td style={{ fontVariantNumeric: "tabular-nums" }}>{d.total_units.toLocaleString()}</td>
                <td style={{ fontVariantNumeric: "tabular-nums", fontSize: 12 }}>${(d.rate ?? 0).toFixed(6)}</td>
                <td style={{ fontVariantNumeric: "tabular-nums" }}>{d.recipients}</td>
                <td style={{ fontSize: 12, color: "var(--text-3)" }}>{d.note || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------- 買い取り申請 ---------- */

function BuybacksCard({ buybacks, filter, setFilter, notify, onChange }: {
  buybacks: PortalBuyback[]; filter: string; setFilter: (s: string) => void;
  notify: Props["notify"]; onChange: () => void;
}) {
  const [busyId, setBusyId] = useState<number | null>(null);

  async function updateStatus(b: PortalBuyback, status: string) {
    if (status === b.status) return;
    setBusyId(b.id);
    try {
      await api.portal.updateBuyback(b.id, status);
      notify(`買い取り申請 #${b.id} を「${BUYBACK_LABELS[status] || status}」に更新しました`, "success");
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
        <h3>買い取り申請（パチスロホイホイ）</h3>
        <select className="input" style={{ width: 140, padding: "6px 10px" }} value={filter}
          onChange={(e) => setFilter(e.target.value)}>
          <option value="">すべて</option>
          {BUYBACK_STATUSES.map((s) => <option key={s} value={s}>{BUYBACK_LABELS[s]}</option>)}
        </select>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 55 }}>ID</th>
              <th>会員</th>
              <th style={{ width: 80 }}>口数</th>
              <th style={{ width: 140 }}>申請日時</th>
              <th style={{ width: 110 }}>状態</th>
              <th style={{ width: 150 }}>状態を変更</th>
            </tr>
          </thead>
          <tbody>
            {buybacks.length === 0 ? (
              <tr><td colSpan={6}><Empty icon={<I.Inbox />} title="買い取り申請はまだありません" /></td></tr>
            ) : buybacks.map((b) => (
              <tr key={b.id}>
                <td style={{ fontVariantNumeric: "tabular-nums" }}>#{b.id}</td>
                <td>
                  <div style={{ fontWeight: 600 }}>{b.name || "—"}</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{b.email}</div>
                </td>
                <td style={{ fontVariantNumeric: "tabular-nums" }}><b>{b.units ?? "—"}</b></td>
                <td><span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtDate(b.requested_at)}</span></td>
                <td><span className={`badge ${statusBadgeClass(b.status)}`}>{BUYBACK_LABELS[b.status] || b.status}</span></td>
                <td>
                  <select className="input" style={{ width: "100%", padding: "6px 8px" }}
                    value={b.status} disabled={busyId === b.id}
                    onChange={(e) => updateStatus(b, e.target.value)}>
                    {BUYBACK_STATUSES.map((s) => <option key={s} value={s}>{BUYBACK_LABELS[s]}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------- 出金申請 ---------- */

function WithdrawalsCard({ withdrawals, filter, setFilter, notify, onChange }: {
  withdrawals: PortalWithdrawal[]; filter: string; setFilter: (s: string) => void;
  notify: Props["notify"]; onChange: () => void;
}) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [paidConfirm, setPaidConfirm] = useState<PortalWithdrawal | null>(null);

  async function updateStatus(w: PortalWithdrawal, status: string) {
    if (status === w.status) return;
    if (status === "paid") { setPaidConfirm(w); return; }
    await applyStatus(w, status);
  }

  async function applyStatus(w: PortalWithdrawal, status: string) {
    setBusyId(w.id);
    try {
      await api.portal.updateWithdrawal(w.id, status);
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
        <h3>ポータル出金申請</h3>
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
            {paidConfirm.name || paidConfirm.email} さんの残高から <b>${paidConfirm.amount.toLocaleString("ja-JP", { minimumFractionDigits: 2 })} USDT</b> が差し引かれます。
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

/* ---------- 会員検索 ---------- */

function MemberSearchCard({ notify }: { notify: Props["notify"] }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<PortalMemberRow[]>([]);
  const [detail, setDetail] = useState<PortalMemberDetail | null>(null);
  const [busy, setBusy] = useState(false);

  async function search() {
    setBusy(true); setDetail(null);
    try {
      const r = await api.portal.members(q);
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
      setDetail(await api.portal.memberDetail(email));
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="card-head"><h3>ポータル会員検索</h3></div>
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
                  <th style={{ width: 120 }}>累計受取</th>
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
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>${m.cumulative_reward.toLocaleString("ja-JP", { minimumFractionDigits: 2 })}</td>
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
              <span>累計受取 <b style={{ fontVariantNumeric: "tabular-nums" }}>${detail.cumulative_reward.toLocaleString("ja-JP", { minimumFractionDigits: 2 })}</b></span>
              <span>受取明細 <b>{detail.history.length}</b> 件</span>
              <span>出金申請 <b>{detail.withdrawals.length + detail.legacy_withdrawals.length}</b> 件</span>
            </div>
            {detail.assets.length > 0 && (
              <table className="tbl" style={{ marginTop: 12 }}>
                <thead>
                  <tr><th>NFT種別</th><th style={{ width: 90 }}>購入</th><th style={{ width: 90 }}>ステーク</th><th style={{ width: 90 }}>未ステーク</th></tr>
                </thead>
                <tbody>
                  {detail.assets.map((a) => (
                    <tr key={a.nft_type}>
                      <td>{NFT_LABELS[a.nft_type] || a.nft_type}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{a.purchased_units}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}><b>{a.staked_units}</b></td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{a.unstaked_units}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {detail.buybacks.length > 0 && (
              <div style={{ marginTop: 10, fontSize: 12.5 }}>
                買い取り申請: {detail.buybacks.map((b) => (
                  <span key={b.id} className={`badge ${statusBadgeClass(b.status)}`} style={{ marginRight: 6 }}>
                    {NFT_LABELS[b.nft_type] || b.nft_type} {b.units}口 — {BUYBACK_LABELS[b.status] || b.status}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
