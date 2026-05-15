"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { WithdrawsList } from "@/lib/types";
import { fmtDate } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Empty } from "../common";

type Props = {
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

const STATUS_LABEL: Record<number, { text: string; cls: string }> = {
  0: { text: "申請中", cls: "badge-warning" },
  1: { text: "処理中", cls: "badge-info" },
  2: { text: "完了", cls: "badge-success" },
  3: { text: "却下", cls: "badge-danger" },
};

export default function WithdrawsTab({ notify }: Props) {
  const [data, setData] = useState<WithdrawsList | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  async function reload() {
    setLoading(true);
    try {
      const r = await api.withdraws.list(500);
      setData(r);
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload(); }, []);

  const filtered = (data?.items || []).filter((w) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      (w.email || "").toLowerCase().includes(s) ||
      (w.name || "").toLowerCase().includes(s) ||
      (w.destination || "").toLowerCase().includes(s)
    );
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">買い取り出金履歴</h1>
          <div className="page-sub">
            nftportal.site 経由で会員権NFT保有者へ支払われた買い取り資金の履歴（30分ごとに自動同期）
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn ghost" onClick={reload} disabled={loading}>
            <I.Refresh /> 更新
          </button>
        </div>
      </div>

      {data && (
        <div className="stat-grid">
          <div className="stat">
            <div className="stat-label">支払い件数</div>
            <div className="stat-value">{data.total_count}</div>
            <div className="stat-delta">total requests</div>
          </div>
          <div className="stat">
            <div className="stat-label">支払い累計</div>
            <div className="stat-value">${data.total_usdt.toLocaleString()}</div>
            <div className="stat-delta">USDT</div>
          </div>
          <div className="stat">
            <div className="stat-label">受取人</div>
            <div className="stat-value">{data.by_recipient.length}</div>
            <div className="stat-delta">unique recipients</div>
          </div>
          <div className="stat">
            <div className="stat-label">平均額/件</div>
            <div className="stat-value">
              ${data.total_count > 0 ? Math.round(data.total_usdt / data.total_count).toLocaleString() : 0}
            </div>
            <div className="stat-delta">USDT</div>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20, marginTop: 20 }}>
        <div className="card">
          <div className="card-head">
            <h3>出金申請一覧</h3>
            <div className="card-head-actions">
              <input
                className="input"
                placeholder="名前・メール・宛先で検索"
                style={{ width: 240 }}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 140 }}>申請日</th>
                  <th>受取人</th>
                  <th style={{ width: 110 }}>金額</th>
                  <th>宛先ウォレット</th>
                  <th style={{ width: 90 }}>状態</th>
                  <th style={{ width: 140 }}>処理日</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan={6}><Empty icon={<I.Inbox />} title="該当する出金申請がありません" /></td></tr>
                ) : filtered.map((w) => {
                  const s = STATUS_LABEL[w.status ?? -1] || { text: String(w.status ?? "?"), cls: "badge-neutral" };
                  return (
                    <tr key={w.id}>
                      <td>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>
                          {fmtDate(w.requested_at || "")}
                        </span>
                      </td>
                      <td>
                        <div><b>{w.name || "(名前なし)"}</b></div>
                        <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{w.email}</div>
                      </td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>
                        <b>${w.amount_usdt.toLocaleString()}</b>
                        <span style={{ color: "var(--text-3)", fontSize: 11, marginLeft: 4 }}>USDT</span>
                      </td>
                      <td>
                        {w.destination ? (
                          <span
                            style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-3)" }}
                            title={w.destination}
                          >
                            {w.destination.slice(0, 8)}...{w.destination.slice(-6)}
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-4)" }}>—</span>
                        )}
                      </td>
                      <td><span className={`badge ${s.cls}`}>{s.text}</span></td>
                      <td>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>
                          {fmtDate(w.action_at || "")}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>受取人ランキング</h3>
            <span className="badge badge-neutral">{data?.by_recipient.length || 0}</span>
          </div>
          <div className="card-body flush">
            {(data?.by_recipient || []).length === 0 ? (
              <Empty icon={<I.Users />} title="まだ受取人なし" />
            ) : (data?.by_recipient || []).map((r, i) => (
              <div
                key={r.email}
                style={{
                  padding: "10px 16px", fontSize: 12.5,
                  borderBottom: i < (data?.by_recipient.length || 0) - 1 ? "1px solid var(--border)" : "none",
                  display: "flex", alignItems: "center", gap: 10,
                }}
              >
                <span style={{ color: "var(--text-4)", fontFamily: "var(--font-mono)", fontSize: 11, width: 18 }}>
                  {i + 1}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500 }}>{r.name || "(名前なし)"}</div>
                  <div style={{ fontSize: 11, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.email}
                  </div>
                </div>
                <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  <div style={{ fontWeight: 600 }}>${r.total_usdt.toLocaleString()}</div>
                  <div style={{ fontSize: 11, color: "var(--text-3)" }}>{r.count} 回</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
