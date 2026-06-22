"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { LuckyAdminSummary, LuckyDistribution } from "@/lib/types";
import { fmtDate } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Empty } from "../common";

type Props = {
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

export default function LuckyTab({ notify }: Props) {
  const [summary, setSummary] = useState<LuckyAdminSummary | null>(null);
  const [dists, setDists] = useState<LuckyDistribution[]>([]);
  const [loading, setLoading] = useState(false);
  const [amount, setAmount] = useState("352");
  const [confirming, setConfirming] = useState(false);
  const [forceNeeded, setForceNeeded] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const [s, d] = await Promise.all([api.lucky.summary(), api.lucky.distributions(60)]);
      setSummary(s);
      setDists(d.distributions);
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload(); }, []);

  const totalNft = summary?.totals.total_nft || 0;
  const amountNum = parseFloat(amount) || 0;
  const rate = totalNft > 0 ? amountNum / totalNft : 0;

  async function doDistribute(force: boolean) {
    if (amountNum <= 0) { notify("金額を入力してください", "error"); return; }
    setSubmitting(true);
    try {
      const r = await api.lucky.distribute(amountNum, force);
      notify(
        `分配しました: ${r.recipients}名 / ${r.total_nft}枚 / 計$${r.distributed_total.toLocaleString()} USDT`,
        "success"
      );
      setConfirming(false);
      setForceNeeded(false);
      await reload();
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
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">ラッキーマスタード 報酬</h1>
          <div className="page-sub">
            会員のステーク枚数に応じた日次報酬を分配します（自動: 毎晩20時。ここから手動実行も可能）
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn ghost" onClick={reload} disabled={loading}>
            <I.Refresh /> 更新
          </button>
        </div>
      </div>

      {summary && (
        <div className="stat-grid">
          <div className="stat">
            <div className="stat-label">報酬対象会員</div>
            <div className="stat-value">{summary.totals.members.toLocaleString()}</div>
            <div className="stat-delta">名（NFT保有）</div>
          </div>
          <div className="stat">
            <div className="stat-label">総ステークNFT</div>
            <div className="stat-value">{summary.totals.total_nft.toLocaleString()}</div>
            <div className="stat-delta">枚（按分の母数）</div>
          </div>
          <div className="stat">
            <div className="stat-label">会員残高合計</div>
            <div className="stat-value">${Math.round(summary.totals.total_balance).toLocaleString()}</div>
            <div className="stat-delta">USDT</div>
          </div>
          <div className="stat">
            <div className="stat-label">累計報酬</div>
            <div className="stat-value">${Math.round(summary.totals.total_reward).toLocaleString()}</div>
            <div className="stat-delta">USDT 配布済</div>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 20, marginTop: 20 }}>
        {/* 分配実行 */}
        <div className="card">
          <div className="card-head"><h3>報酬を分配</h3></div>
          <div className="card-body">
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-3)", marginBottom: 6 }}>
              分配総額（USDT / 日）
            </label>
            <input
              className="input"
              type="number"
              min={1}
              value={amount}
              onChange={(e) => { setAmount(e.target.value); setConfirming(false); setForceNeeded(false); }}
              style={{ width: "100%" }}
            />
            <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 10, lineHeight: 1.7 }}>
              対象 <b>{summary?.totals.members ?? "—"}</b> 名 / <b>{totalNft.toLocaleString()}</b> 枚<br />
              1枚あたり <b>${rate.toFixed(4)}</b> / 日
            </div>

            {summary?.latest_distribution && (
              <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 10 }}>
                最終分配: {fmtDate(summary.latest_distribution.distributed_for || "")}
                （{summary.latest_distribution.created_by}）
              </div>
            )}

            {!confirming && !forceNeeded && (
              <button
                className="btn primary"
                style={{ width: "100%", marginTop: 14 }}
                onClick={() => setConfirming(true)}
                disabled={amountNum <= 0 || totalNft <= 0}
              >
                <I.DollarSign /> 分配を実行する
              </button>
            )}

            {confirming && !forceNeeded && (
              <div style={{ marginTop: 14, padding: 12, background: "var(--bg-inset)", borderRadius: 8, border: "1px solid var(--border)" }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>本日分を分配しますか？</div>
                <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 10 }}>
                  {summary?.totals.members}名へ合計 約${(rate * totalNft).toFixed(2)} USDT を加算します。
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
                  ⚠️ 本日は既に分配済みです
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

        {/* 分配履歴 */}
        <div className="card">
          <div className="card-head">
            <h3>分配履歴</h3>
            <span className="badge badge-neutral">{dists.length}</span>
          </div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 150 }}>分配日時</th>
                  <th style={{ width: 100 }}>総額</th>
                  <th style={{ width: 80 }}>NFT枚数</th>
                  <th style={{ width: 90 }}>単価</th>
                  <th style={{ width: 70 }}>受取</th>
                  <th>実行</th>
                </tr>
              </thead>
              <tbody>
                {dists.length === 0 ? (
                  <tr><td colSpan={6}><Empty icon={<I.Inbox />} title="分配履歴がありません" /></td></tr>
                ) : dists.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>
                        {fmtDate(d.distributed_for || d.created_at)}
                      </span>
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      <b>${d.pool_amount.toLocaleString()}</b>
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{d.total_nft.toLocaleString()}</td>
                    <td style={{ fontVariantNumeric: "tabular-nums", fontSize: 12 }}>
                      ${(d.rate ?? 0).toFixed(4)}
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{d.recipients}</td>
                    <td>
                      <span className={`badge ${d.created_by === "cron" ? "badge-info" : d.created_by === "migration" ? "badge-neutral" : "badge-success"}`}>
                        {d.created_by === "cron" ? "自動" : d.created_by === "migration" ? "移行" : "手動"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
