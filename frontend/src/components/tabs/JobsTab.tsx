"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BulkJob } from "@/lib/types";
import { statusInfo, fmtDate } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Empty, Modal } from "../common";

type Props = {
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

export default function JobsTab({ notify }: Props) {
  const [jobs, setJobs] = useState<BulkJob[]>([]);
  const [showDetail, setShowDetail] = useState<BulkJob | null>(null);
  const [cancelling, setCancelling] = useState<number | null>(null);

  async function reload() {
    try { setJobs(await api.send.jobs()); }
    catch (e: any) { notify(e.message, "error"); }
  }
  useEffect(() => {
    reload();
    const h = setInterval(reload, 5000);
    return () => clearInterval(h);
  }, []);

  async function cancelJob(j: BulkJob) {
    const when = j.scheduled_at ? new Date(j.scheduled_at).toLocaleString("ja-JP") : "";
    if (!confirm(`ジョブ #${j.id}（${j.subject}\n予定 ${when}）をキャンセルしますか？`)) return;
    setCancelling(j.id);
    try {
      await api.send.cancel(j.id);
      notify(`ジョブ #${j.id} をキャンセルしました`);
      await reload();
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setCancelling(null);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">送信ジョブ</h1>
          <div className="page-sub">一括送信の進捗・成否をリアルタイムに追跡します。</div>
        </div>
        <div className="page-head-actions">
          <button className="btn ghost" onClick={reload}><I.Refresh /> 更新</button>
        </div>
      </div>

      <div className="card">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 70 }}>ID</th>
                <th style={{ width: 150 }}>作成日時</th>
                <th>件名</th>
                <th style={{ width: 80 }}>対象</th>
                <th>進捗</th>
                <th style={{ width: 100 }}>状態</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr><td colSpan={7}><Empty icon={<I.Truck />} title="ジョブはまだありません" /></td></tr>
              ) : jobs.map((j) => {
                const done = j.sent + j.failed;
                const pct = j.total ? Math.round((done / j.total) * 100) : 0;
                const s = statusInfo(j.status);
                const isScheduled = j.status === "scheduled";
                return (
                  <tr key={j.id}>
                    <td><span style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)" }}>#{j.id}</span></td>
                    <td>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtDate(j.created_at)}</span>
                      {j.scheduled_at && (
                        <div style={{ fontSize: 11, color: "var(--warning)", marginTop: 2, display: "flex", alignItems: "center", gap: 4 }}>
                          <I.Clock size={10} /> 予定: {new Date(j.scheduled_at).toLocaleString("ja-JP")}
                        </div>
                      )}
                    </td>
                    <td><b>{j.subject}</b></td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{j.total}</td>
                    <td>
                      {isScheduled ? (
                        <span style={{ fontSize: 12, color: "var(--warning)", display: "inline-flex", alignItems: "center", gap: 4 }}>
                          <I.Clock size={12} /> 待機中
                        </span>
                      ) : (
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span style={{ fontSize: 12, color: "var(--text-2)", fontVariantNumeric: "tabular-nums", minWidth: 60 }}>{done}/{j.total}</span>
                          <div className="progress" style={{ flex: 1, minWidth: 100 }}><div style={{ width: pct + "%" }} /></div>
                          <span style={{ fontSize: 12, color: "var(--text-3)", fontVariantNumeric: "tabular-nums" }}>{pct}%</span>
                          {j.failed > 0 && <span className="badge badge-danger">失敗 {j.failed}</span>}
                        </div>
                      )}
                    </td>
                    <td><span className={`badge ${s.cls} dot`}>{s.label}</span></td>
                    <td>
                      <div className="row-actions">
                        <button className="btn ghost sm" onClick={() => setShowDetail(j)} title="詳細"><I.Eye /></button>
                        {isScheduled && (
                          <button
                            className="btn ghost sm"
                            style={{ color: "var(--danger)" }}
                            disabled={cancelling === j.id}
                            onClick={() => cancelJob(j)}
                            title="予約をキャンセル"
                          >
                            {cancelling === j.id ? <span className="spinner" /> : <I.X />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        open={!!showDetail}
        onClose={() => setShowDetail(null)}
        title={showDetail ? `ジョブ #${showDetail.id} の詳細` : ""}
        width={720}
        footer={<button className="btn ghost" onClick={() => setShowDetail(null)}>閉じる</button>}
      >
        {showDetail && (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
              <Mini label="送信成功" value={showDetail.sent} accent="success" />
              <Mini label="失敗" value={showDetail.failed} accent="danger" />
              <Mini label="対象数" value={showDetail.total} />
            </div>
            <div className="field">
              <label>件名</label>
              <div style={{ fontSize: 14, fontWeight: 500 }}>{showDetail.subject}</div>
            </div>
            <hr />
            <div className="field">
              <label>本文</label>
              <div className="preview-box" style={{ maxHeight: 240 }}>{showDetail.body}</div>
            </div>
            {showDetail.nft_types && (
              <div className="field">
                <label>対象 NFT 種別</label>
                <div style={{ fontSize: 13, color: "var(--text-2)" }}>{showDetail.nft_types || "全員"}</div>
              </div>
            )}
            <div className="field">
              <label>状態 / 作成日時</label>
              <div style={{ fontSize: 13, color: "var(--text-2)" }}>
                {statusInfo(showDetail.status).label} · {fmtDate(showDetail.created_at)}
                {showDetail.finished_at && <> · 完了 {fmtDate(showDetail.finished_at)}</>}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

function Mini({ label, value, accent }: { label: string; value: number | string; accent?: "success" | "danger" }) {
  const color = accent === "success" ? "var(--success)" : accent === "danger" ? "var(--danger)" : "var(--text)";
  return (
    <div style={{ padding: "12px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--bg-soft)" }}>
      <div style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 600, color, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}
