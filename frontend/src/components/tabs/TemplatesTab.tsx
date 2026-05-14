"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Template } from "@/lib/types";
import { fmtDate } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Empty } from "../common";

type Props = {
  templates: Template[];
  notify: (msg: string, type?: "success" | "error" | "info") => void;
  onReload: () => void;
};

export default function TemplatesTab({ templates, notify, onReload }: Props) {
  const [selected, setSelected] = useState<number | null>(templates[0]?.id ?? null);
  const [form, setForm] = useState({ name: "", subject: "", body: "" });
  const [isNew, setIsNew] = useState(false);

  useEffect(() => {
    if (selected == null) {
      if (!isNew) setForm({ name: "", subject: "", body: "" });
      return;
    }
    const t = templates.find((x) => x.id === selected);
    if (t) setForm({ name: t.name, subject: t.subject, body: t.body });
  }, [selected, templates, isNew]);

  function newTemplate() {
    setIsNew(true);
    setSelected(null);
    setForm({ name: "", subject: "", body: "" });
  }

  async function save() {
    if (!form.name.trim() || !form.subject.trim() || !form.body.trim()) {
      notify("すべての項目を入力してください", "error");
      return;
    }
    try {
      const r = await api.templates.upsert(form.name, form.subject, form.body);
      notify("テンプレートを保存しました");
      setIsNew(false);
      onReload();
      setSelected(r.id);
    } catch (e: any) { notify(e.message, "error"); }
  }

  async function remove(id: number) {
    if (!confirm("このテンプレートを削除しますか？")) return;
    try {
      await api.templates.remove(id);
      notify("削除しました");
      setSelected(null);
      setForm({ name: "", subject: "", body: "" });
      onReload();
    } catch (e: any) { notify(e.message, "error"); }
  }

  async function duplicate(t: Template) {
    try {
      await api.templates.upsert(t.name + " (コピー)", t.subject, t.body);
      notify("複製しました");
      onReload();
    } catch (e: any) { notify(e.message, "error"); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">テンプレート</h1>
          <div className="page-sub">件名・本文を保存して再利用できます。プレースホルダにも対応。</div>
        </div>
        <div className="page-head-actions">
          <button className="btn primary" onClick={newTemplate}><I.Plus /> 新規テンプレート</button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 20 }}>
        <div className="card">
          <div className="card-head">
            <h3>一覧</h3>
            <span className="badge badge-neutral">{templates.length}</span>
          </div>
          <div className="card-body flush">
            {templates.length === 0 ? (
              <Empty icon={<I.FileText />} title="テンプレートがありません" sub="右上から作成できます。" />
            ) : templates.map((t) => (
              <div
                key={t.id}
                onClick={() => { setSelected(t.id); setIsNew(false); }}
                style={{
                  padding: "12px 16px",
                  borderBottom: "1px solid var(--border)",
                  cursor: "pointer",
                  background: selected === t.id ? "var(--accent-soft)" : "transparent",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                  <b style={{ fontSize: 13.5, color: selected === t.id ? "var(--accent-text)" : "var(--text)" }}>{t.name}</b>
                  <button
                    className="icon-btn"
                    style={{ marginLeft: "auto", width: 24, height: 24 }}
                    onClick={(e) => { e.stopPropagation(); duplicate(t); }}
                    title="複製"
                  >
                    <I.Copy size={12} />
                  </button>
                </div>
                <div style={{ fontSize: 12, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.subject}</div>
                <div style={{ fontSize: 11, color: "var(--text-4)", marginTop: 4 }}>{fmtDate(t.updated_at)}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>{isNew ? "新規テンプレート" : selected ? "編集" : "選択してください"}</h3>
            {selected && (
              <div className="card-head-actions">
                <button className="btn ghost sm" style={{ color: "var(--danger)" }} onClick={() => remove(selected)}>
                  <I.Trash /> 削除
                </button>
              </div>
            )}
          </div>
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {!selected && !isNew ? (
              <Empty icon={<I.FileText />} title="左の一覧から選択するか、新規作成してください" />
            ) : (
              <>
                <div className="field">
                  <label>テンプレート名</label>
                  <input
                    className="input"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="例: 月次案内"
                  />
                </div>
                <div className="field">
                  <label>件名</label>
                  <input className="input" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} />
                </div>
                <div className="field">
                  <label>本文</label>
                  <textarea
                    className="textarea"
                    value={form.body}
                    onChange={(e) => setForm({ ...form, body: e.target.value })}
                    style={{ minHeight: 220 }}
                  />
                  <div className="field-hint">
                    プレースホルダ:
                    <span className="kbd">{"{name}"}</span>
                    <span className="kbd" style={{ marginLeft: 4 }}>{"{nft_type}"}</span>
                    <span className="kbd" style={{ marginLeft: 4 }}>{"{email}"}</span>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button className="btn primary" onClick={save}><I.Save /> 保存</button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
