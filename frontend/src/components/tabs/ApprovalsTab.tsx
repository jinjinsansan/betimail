"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Approval } from "@/lib/types";
import { fmtDate } from "@/lib/ui";

type Props = {
  notify: (msg: string, err?: boolean) => void;
  onChange: () => void;
};

export default function ApprovalsTab({ notify, onChange }: Props) {
  const [items, setItems] = useState<Approval[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);

  async function reload() {
    try {
      const list = await api.approvals.list();
      setItems(list);
      const d: Record<number, string> = {};
      list.forEach((a) => { d[a.id] = a.ai_draft; });
      setDrafts(d);
    } catch (e: any) { notify(e.message, true); }
  }

  useEffect(() => { reload(); }, []);

  async function approve(id: number) {
    setBusy(id);
    try {
      await api.approvals.approve(id);
      notify("送信しました");
      await reload(); onChange();
    } catch (e: any) { notify(e.message, true); }
    finally { setBusy(null); }
  }

  async function editSend(id: number) {
    const body = drafts[id];
    if (!body?.trim()) { notify("本文が空です", true); return; }
    setBusy(id);
    try {
      await api.approvals.edit(id, body);
      notify("編集内容で送信しました");
      await reload(); onChange();
    } catch (e: any) { notify(e.message, true); }
    finally { setBusy(null); }
  }

  async function reject(id: number) {
    if (!confirm("この返信を却下しますか？")) return;
    setBusy(id);
    try {
      await api.approvals.reject(id);
      notify("却下しました");
      await reload(); onChange();
    } catch (e: any) { notify(e.message, true); }
    finally { setBusy(null); }
  }

  return (
    <div className="card">
      <h2>承認待ち（AI生成下書き）
        <div className="actions">
          <button className="btn secondary small" onClick={reload}>🔄 更新</button>
        </div>
      </h2>
      <p className="hint">受信メールに対するAI返信のうち、AIが自信を持てない・人手確認が必要と判断したもの。</p>
      <div style={{ marginTop: 16 }}>
        {items.length === 0 ? (
          <p className="placeholder">承認待ちの返信はありません。</p>
        ) : items.map((a) => (
          <div className="approval" key={a.id}>
            <div className="meta">
              <span className="from">{a.sender_name || "不明"} &lt;{a.sender_email}&gt;</span>
              <span>件名: <b>{a.original_subject || "(なし)"}</b></span>
              <span style={{ color: "var(--text-faint)" }}>受信: {fmtDate(a.created_at)}</span>
            </div>
            <details>
              <summary>受信メール本文を見る</summary>
              <div className="body-display">{a.original_body || ""}</div>
            </details>
            <label>AI下書き（編集可）</label>
            <textarea value={drafts[a.id] ?? ""} onChange={(e) => setDrafts((d) => ({ ...d, [a.id]: e.target.value }))} />
            <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn success" disabled={busy === a.id} onClick={() => approve(a.id)}>
                {busy === a.id ? <><span className="spinner" /> 処理中…</> : "✅ そのまま送信"}
              </button>
              <button className="btn" disabled={busy === a.id} onClick={() => editSend(a.id)}>✏️ 編集内容で送信</button>
              <button className="btn danger" disabled={busy === a.id} onClick={() => reject(a.id)}>❌ 却下</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
