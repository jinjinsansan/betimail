"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { WithdrawsList } from "@/lib/types";
import { fmtDate } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Empty } from "../common";

type Props = {
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

// AFI(afi.irah.uk) の status は status_request: 1=未承認 / 2=承認済
const AFI_STATUS: Record<number, { text: string; cls: string }> = {
  1: { text: "未承認", cls: "badge-warning" },
  2: { text: "承認済", cls: "badge-success" },
};

const AFI_ID_OFFSET = 1_000_000_000; // sync 側で付与した offset（元の req_id に戻すため）

export default function AfiWithdrawsTab({ notify }: Props) {
  const [data, setData] = useState<WithdrawsList | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [pendingOnly, setPendingOnly] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const r = await api.withdraws.list(5000, undefined, "afi");
      setData(r);
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  const items = data?.items || [];

  const pending = useMemo(() => items.filter((w) => w.status === 1), [items]);
  const pendingSum = useMemo(
    () => pending.reduce((acc, w) => acc + (w.amount_usdt || 0), 0),
    [pending]
  );

  const filtered = items.filter((w) => {
    if (pendingOnly && w.status !== 1) return false;
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
          <h1 className="page-title">アフィリエイト出金 (afi.irah.uk)</h1>
          <div className="page-sub">
            afi.irah.uk のアフィリエイト出金申請（閲覧専用・15分/45分ごとに自動同期）。
            ポータルサイトの買い取り出金とは別系統です。
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
            <div className="stat-label">総申請件数</div>
            <div className="stat-value">{data.total_count.toLocaleString()}</div>
            <div className="stat-delta">all requests</div>
          </div>
          <div className="stat">
            <div className="stat-label">総額</div>
            <div className="stat-value">${data.total_usdt.toLocaleString()}</div>
            <div className="stat-delta">USDT</div>
          </div>
          <div className="stat">
            <div className="stat-label">未承認 件数</div>
            <div className="stat-value" style={{ color: "var(--warning, #b8860b)" }}>
              {pending.length.toLocaleString()}
            </div>
            <div className="stat-delta">status_request = 1</div>
          </div>
          <div className="stat">
            <div className="stat-label">未承認 金額</div>
            <div className="stat-value" style={{ color: "var(--warning, #b8860b)" }}>
              ${pendingSum.toLocaleString()}
            </div>
            <div className="stat-delta">USDT (未出金)</div>
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-head">
          <h3>出金申請一覧</h3>
          <div className="card-head-actions" style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--text-2)" }}>
              <input
                type="checkbox"
                checked={pendingOnly}
                onChange={(e) => setPendingOnly(e.target.checked)}
              />
              未承認のみ表示
            </label>
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
                <th style={{ width: 80 }}>req_id</th>
                <th style={{ width: 140 }}>申請日</th>
                <th>申請者</th>
                <th style={{ width: 120 }}>金額</th>
                <th>宛先ウォレット</th>
                <th style={{ width: 90 }}>状態</th>
                <th style={{ width: 140 }}>処理日</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <Empty icon={<I.Inbox />} title="該当する出金申請がありません" />
                  </td>
                </tr>
              ) : (
                filtered.map((w) => {
                  const s =
                    AFI_STATUS[w.status ?? -1] || {
                      text: String(w.status ?? "?"),
                      cls: "badge-neutral",
                    };
                  const reqId = w.external_id ? w.external_id - AFI_ID_OFFSET : "—";
                  return (
                    <tr key={w.id}>
                      <td>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>
                          {reqId}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>
                          {fmtDate(w.requested_at || "")}
                        </span>
                      </td>
                      <td>
                        <div>
                          <b>{w.name || "(名前なし)"}</b>
                        </div>
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
                      <td>
                        <span className={`badge ${s.cls}`}>{s.text}</span>
                      </td>
                      <td>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>
                          {fmtDate(w.action_at || "")}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
