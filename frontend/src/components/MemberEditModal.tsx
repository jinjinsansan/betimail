"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Member, MemberHistory } from "@/lib/types";
import { NFT_TYPES, fmtDate, statusInfo } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Modal } from "./common";

type Props = {
  email: string | null;
  mode: "edit" | "add";
  onClose: () => void;
  onSaved: () => void;
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

const EMPTY: Member = {
  name: "", email: "", nft_type: NFT_TYPES[0],
  joined_date: new Date().toISOString().slice(0, 10), notes: "",
};

export default function MemberEditModal({ email, mode, onClose, onSaved, notify }: Props) {
  const isEdit = mode === "edit";
  const [form, setForm] = useState<Member>(EMPTY);
  const [history, setHistory] = useState<MemberHistory | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(isEdit);

  useEffect(() => {
    if (!isEdit || !email) {
      setForm({ ...EMPTY });
      setHistory(null);
      return;
    }
    setLoading(true);
    api.members.history(email)
      .then((data) => {
        setForm(data.member);
        setHistory(data);
      })
      .catch((e) => { notify(e.message, "error"); onClose(); })
      .finally(() => setLoading(false));
  }, [email, isEdit]);

  function setField<K extends keyof Member>(k: K, v: Member[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function save() {
    if (!form.name || !form.email) {
      notify("名前とメールアドレスは必須です", "error");
      return;
    }
    setSaving(true);
    try {
      if (isEdit && email) {
        await api.members.update(email, form);
        notify("更新しました");
      } else {
        await api.members.add(form);
        notify(`${form.name} を追加しました`);
      }
      onSaved();
    } catch (e: any) { notify(e.message, "error"); }
    finally { setSaving(false); }
  }

  const events = history ? [
    ...history.sent.map((s) => ({ ts: s.sent_at, dir: "送信", subject: s.subject, status: s.status })),
    ...history.received.map((r) => ({ ts: r.received_at, dir: "受信", subject: r.subject, status: r.status })),
  ].sort((a, b) => (b.ts || "").localeCompare(a.ts || "")) : [];

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? "メンバー編集" : "メンバー追加"}
      width={680}
      footer={
        <>
          <button className="btn ghost" onClick={onClose}>キャンセル</button>
          <button className="btn primary" onClick={save} disabled={saving || !form.name || !form.email}>
            {saving ? <><span className="spinner" /> 保存中…</> : <><I.Save /> 保存</>}
          </button>
        </>
      }
    >
      {loading ? (
        <p style={{ color: "var(--text-3)", padding: 24, textAlign: "center" }}>読み込み中…</p>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div className="field">
              <label>名前</label>
              <input className="input" value={form.name} onChange={(e) => setField("name", e.target.value)} placeholder="山田太郎" />
            </div>
            <div className="field">
              <label>メールアドレス</label>
              <input className="input" type="email" value={form.email} onChange={(e) => setField("email", e.target.value)} placeholder="yamada@example.com" />
            </div>
            <div className="field">
              <label>NFT種別</label>
              <select className="select" value={form.nft_type} onChange={(e) => setField("nft_type", e.target.value)}>
                {NFT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="field">
              <label>購入日</label>
              <input className="input" type="date" value={form.joined_date} onChange={(e) => setField("joined_date", e.target.value)} />
            </div>
            <div className="field" style={{ gridColumn: "1 / -1" }}>
              <label>備考</label>
              <input className="input" value={form.notes} onChange={(e) => setField("notes", e.target.value)} placeholder="任意" />
            </div>
          </div>

          {isEdit && events.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 12, color: "var(--text-2)", fontWeight: 500, marginBottom: 8 }}>
                過去のやり取り（最新 {Math.min(events.length, 20)} 件）
              </div>
              <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
                {events.slice(0, 20).map((h, i) => {
                  const s = statusInfo(h.status);
                  return (
                    <div
                      key={i}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "10px 12px", fontSize: 12.5,
                        borderBottom: i < Math.min(events.length, 20) - 1 ? "1px solid var(--border)" : "none",
                        background: i % 2 ? "var(--bg-soft)" : "var(--bg-elev)",
                      }}
                    >
                      <span style={{ color: "var(--text-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>{fmtDate(h.ts)}</span>
                      <span className={`badge ${h.dir === "送信" ? "badge-info" : "badge-neutral"}`}>{h.dir}</span>
                      <b style={{ flex: 1 }}>{h.subject || "(件名なし)"}</b>
                      <span className={`badge ${s.cls}`}>{s.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
