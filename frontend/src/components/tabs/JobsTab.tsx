"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BulkJob } from "@/lib/types";
import { fmtDate } from "@/lib/ui";

type Props = {
  notify: (msg: string, err?: boolean) => void;
};

export default function JobsTab({ notify }: Props) {
  const [jobs, setJobs] = useState<BulkJob[]>([]);

  async function reload() {
    try { setJobs(await api.send.jobs()); }
    catch (e: any) { notify(e.message, true); }
  }
  useEffect(() => {
    reload();
    const h = setInterval(reload, 5000);
    return () => clearInterval(h);
  }, []);

  return (
    <div className="card">
      <h2>一括送信ジョブ
        <div className="actions">
          <button className="btn secondary small" onClick={reload}>🔄 更新</button>
        </div>
      </h2>
      <table>
        <thead><tr><th>ID</th><th>作成日時</th><th>件名</th><th>対象</th><th>進捗</th><th>状態</th></tr></thead>
        <tbody>
          {jobs.length === 0 ? (
            <tr><td colSpan={6} className="placeholder">ジョブなし</td></tr>
          ) : jobs.map((j) => {
            const done = j.sent + j.failed;
            const pct = j.total === 0 ? 0 : Math.round((done / j.total) * 100);
            return (
              <tr key={j.id}>
                <td>{j.id}</td>
                <td>{fmtDate(j.created_at)}</td>
                <td>{j.subject}</td>
                <td>{j.total} 名</td>
                <td>
                  {done}/{j.total} ({pct}%) <span style={{ color: "var(--success)" }}>✅{j.sent}</span>{" "}
                  <span style={{ color: "var(--error)" }}>❌{j.failed}</span>
                  <div className="progress-bar"><div style={{ width: `${pct}%` }} /></div>
                </td>
                <td>
                  {j.status === "done"
                    ? <><span className="status-dot dot-sent"></span>完了</>
                    : <><span className="status-dot dot-pending"></span>実行中</>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
