"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Template } from "@/lib/types";
import { fmtDate } from "@/lib/ui";

type Props = {
  templates: Template[];
  notify: (msg: string, err?: boolean) => void;
  onReload: () => void;
};

export default function TemplatesTab({ templates, notify, onReload }: Props) {
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");

  async function save() {
    if (!name.trim() || !subject.trim() || !body.trim()) {
      notify("すべての項目を入力してください", true);
      return;
    }
    try {
      await api.templates.upsert(name, subject, body);
      notify("テンプレートを保存しました");
      onReload();
    } catch (e: any) { notify(e.message, true); }
  }

  async function remove(id: number) {
    if (!confirm("このテンプレートを削除しますか？")) return;
    try {
      await api.templates.remove(id);
      notify("削除しました");
      onReload();
    } catch (e: any) { notify(e.message, true); }
  }

  function loadToForm(t: Template) {
    setName(t.name); setSubject(t.subject); setBody(t.body);
  }

  return (
    <>
      <div className="card">
        <h2>テンプレート編集</h2>
        <label>テンプレート名</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例: 月次案内" />
        <label>件名</label>
        <input value={subject} onChange={(e) => setSubject(e.target.value)} />
        <label>本文</label>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="本文（{name} などのプレースホルダ使用可）" />
        <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
          <button className="btn" onClick={save}>保存</button>
          <button className="btn secondary" onClick={() => { setName(""); setSubject(""); setBody(""); }}>クリア</button>
        </div>
      </div>

      <div className="card">
        <h2>テンプレート一覧</h2>
        <table>
          <thead><tr><th>名前</th><th>件名</th><th>更新日</th><th></th></tr></thead>
          <tbody>
            {templates.length === 0 ? (
              <tr><td colSpan={4} className="placeholder">テンプレートなし</td></tr>
            ) : templates.map((t) => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td>{t.subject}</td>
                <td>{fmtDate(t.updated_at)}</td>
                <td>
                  <button className="btn small secondary" onClick={() => loadToForm(t)}>編集</button>
                  <button className="btn small danger" style={{ marginLeft: 6 }} onClick={() => remove(t.id)}>削除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
