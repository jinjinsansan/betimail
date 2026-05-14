"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Approval } from "@/lib/types";
import { fmtDate, memberInitial } from "@/lib/ui";
import { I } from "@/lib/icons";
import { ConfBar, Empty } from "../common";

type Props = {
  notify: (msg: string, type?: "success" | "error" | "info") => void;
  onChange: () => void;
};

export default function ApprovalsTab({ notify, onChange }: Props) {
  const [items, setItems] = useState<Approval[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "low" | "mid" | "high">("all");

  async function reload() {
    try {
      const list = await api.approvals.list();
      setItems(list);
      const d: Record<number, string> = {};
      list.forEach((a) => { d[a.id] = a.ai_draft; });
      setDrafts(d);
      if (list.length > 0 && expanded == null) setExpanded(list[0].id);
    } catch (e: any) { notify(e.message, "error"); }
  }

  useEffect(() => { reload(); }, []);

  async function approve(a: Approval) {
    setBusy(a.id);
    try {
      await api.approvals.approve(a.id);
      notify(`${a.sender_name || a.sender_email} 宛に送信しました`);
      await reload(); onChange();
    } catch (e: any) { notify(e.message, "error"); }
    finally { setBusy(null); }
  }

  async function editSend(a: Approval) {
    const body = drafts[a.id];
    if (!body?.trim()) { notify("本文が空です", "error"); return; }
    setBusy(a.id);
    try {
      await api.approvals.edit(a.id, body);
      notify("編集内容で送信しました");
      await reload(); onChange();
    } catch (e: any) { notify(e.message, "error"); }
    finally { setBusy(null); }
  }

  async function reject(a: Approval) {
    if (!confirm("この返信を却下しますか？")) return;
    setBusy(a.id);
    try {
      await api.approvals.reject(a.id);
      notify("却下しました");
      await reload(); onChange();
    } catch (e: any) { notify(e.message, "error"); }
    finally { setBusy(null); }
  }

  const counts = {
    all: items.length,
    low: items.filter((a) => (a.ai_confidence ?? 0) < 0.5).length,
    mid: items.filter((a) => {
      const c = a.ai_confidence ?? 0;
      return c >= 0.5 && c < 0.8;
    }).length,
    high: items.filter((a) => (a.ai_confidence ?? 0) >= 0.8).length,
  };

  const filtered = items.filter((a) => {
    const c = a.ai_confidence ?? 0;
    if (filter === "low") return c < 0.5;
    if (filter === "mid") return c >= 0.5 && c < 0.8;
    if (filter === "high") return c >= 0.8;
    return true;
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">承認待ち</h1>
          <div className="page-sub">AI が自信を持てない・人手確認が必要と判断した返信を確認・編集・送信できます。</div>
        </div>
        <div className="page-head-actions">
          <button className="btn ghost" onClick={reload}><I.Refresh /> 更新</button>
        </div>
      </div>

      <div className="card">
        <div className="filter-bar">
          <div className="chip-row">
            <div className={`chip ${filter === "all" ? "active" : ""}`} onClick={() => setFilter("all")}>
              すべて <span className="chip-count">· {counts.all}</span>
            </div>
            <div className={`chip ${filter === "low" ? "active" : ""}`} onClick={() => setFilter("low")}>
              低信頼度 <span className="chip-count">· {counts.low}</span>
            </div>
            <div className={`chip ${filter === "mid" ? "active" : ""}`} onClick={() => setFilter("mid")}>
              中 <span className="chip-count">· {counts.mid}</span>
            </div>
            <div className={`chip ${filter === "high" ? "active" : ""}`} onClick={() => setFilter("high")}>
              高 <span className="chip-count">· {counts.high}</span>
            </div>
          </div>
          <span className="count">{filtered.length} 件</span>
        </div>

        <div className="card-body" style={{ paddingTop: 16 }}>
          {filtered.length === 0 ? (
            <Empty icon={<I.CheckCircle />} title="承認待ちの返信はありません" sub="AI が自動応答を完了しています。" />
          ) : filtered.map((a) => {
            const isExpanded = expanded === a.id;
            return (
              <div className="approval-item" key={a.id} style={{ marginBottom: 12 }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12, cursor: "pointer" }} onClick={() => setExpanded(isExpanded ? null : a.id)}>
                  <div className="avatar" style={{ width: 32, height: 32, fontSize: 13, background: "var(--bg-inset)", color: "var(--text-2)" }}>
                    {memberInitial({ name: a.sender_name, email: a.sender_email } as any)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <b style={{ fontSize: 14 }}>{a.sender_name || "(名前なし)"}</b>
                      <span style={{ fontSize: 12, color: "var(--text-3)" }}>{a.sender_email}</span>
                      <span style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--text-4)" }}>{fmtDate(a.created_at)}</span>
                    </div>
                    <div style={{ fontSize: 13.5, color: "var(--text-2)", marginTop: 4, fontWeight: 500 }}>
                      {a.original_subject || "(件名なし)"}
                    </div>
                    {a.ai_confidence != null && <div style={{ marginTop: 8 }}><ConfBar value={a.ai_confidence} /></div>}
                  </div>
                  <I.ChevronDown size={16} style={{ color: "var(--text-3)", transform: isExpanded ? "rotate(180deg)" : "none", transition: "transform .15s" }} />
                </div>

                {isExpanded && (
                  <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px dashed var(--border)" }} onClick={(e) => e.stopPropagation()}>
                    <details open>
                      <summary>受信メール本文</summary>
                      <div className="preview-box" style={{ marginTop: 6 }}>{a.original_body || ""}</div>
                    </details>
                    <div className="field" style={{ marginTop: 14 }}>
                      <label><I.Sparkle size={12} /> AI 下書き（編集可）</label>
                      <textarea
                        className="textarea"
                        value={drafts[a.id] ?? a.ai_draft}
                        onChange={(e) => setDrafts((d) => ({ ...d, [a.id]: e.target.value }))}
                      />
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                      <button className="btn success" disabled={busy === a.id} onClick={() => approve(a)}>
                        {busy === a.id ? <><span className="spinner" /> 処理中</> : <><I.Check /> そのまま送信</>}
                      </button>
                      <button className="btn primary" disabled={busy === a.id} onClick={() => editSend(a)}>
                        <I.PenLine /> 編集内容で送信
                      </button>
                      <button className="btn ghost" disabled={busy === a.id} onClick={() => reject(a)} style={{ color: "var(--danger)", marginLeft: "auto" }}>
                        <I.X /> 却下
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
