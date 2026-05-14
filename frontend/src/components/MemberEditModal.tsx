"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Member, MemberHistory } from "@/lib/types";
import { fmtDate, statusBadge } from "@/lib/ui";

type Props = {
  email: string;
  nftTypes: string[];
  onClose: () => void;
  onSaved: () => void;
  notify: (msg: string, err?: boolean) => void;
};

export default function MemberEditModal({ email, nftTypes, onClose, onSaved, notify }: Props) {
  const [member, setMember] = useState<Member | null>(null);
  const [history, setHistory] = useState<MemberHistory | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.members.history(email);
        setMember(data.member);
        setHistory(data);
      } catch (e: any) { notify(e.message, true); onClose(); }
    })();
  }, [email]);

  if (!member) {
    return (
      <div className="modal-backdrop">
        <div className="modal"><p>読み込み中…</p></div>
      </div>
    );
  }

  function setField<K extends keyof Member>(k: K, v: Member[K]) {
    setMember((m) => m ? { ...m, [k]: v } : m);
  }

  async function save() {
    if (!member) return;
    setSaving(true);
    try {
      await api.members.update(email, member);
      notify("更新しました");
      onSaved();
    } catch (e: any) { notify(e.message, true); }
    finally { setSaving(false); }
  }

  const events = history ? [
    ...history.sent.map((s) => ({ ts: s.sent_at, dir: "→送信", subject: s.subject, status: s.status })),
    ...history.received.map((r) => ({ ts: r.received_at, dir: "←受信", subject: r.subject, status: r.status })),
  ].sort((a, b) => (b.ts || "").localeCompare(a.ts || "")) : [];

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>メンバー編集</h3>
        <label>名前</label>
        <input value={member.name} onChange={(e) => setField("name", e.target.value)} />
        <label>メールアドレス</label>
        <input type="email" value={member.email} onChange={(e) => setField("email", e.target.value)} />
        <label>NFT種別</label>
        <select value={member.nft_type} onChange={(e) => setField("nft_type", e.target.value)}>
          {nftTypes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <label>購入日</label>
        <input type="date" value={member.joined_date} onChange={(e) => setField("joined_date", e.target.value)} />
        <label>備考</label>
        <input value={member.notes} onChange={(e) => setField("notes", e.target.value)} />

        {events.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <h4 style={{ color: "var(--accent)", fontSize: "0.85rem", marginBottom: 6 }}>
              過去のやり取り（最新 {events.length} 件）
            </h4>
            <div style={{ maxHeight: 160, overflowY: "auto", fontSize: "0.8rem" }}>
              {events.slice(0, 20).map((e, i) => {
                const sb = statusBadge(e.status);
                return (
                  <div key={i} style={{ padding: "4px 0", borderBottom: "1px solid #1e1e38" }}>
                    <span style={{ color: "var(--text-dim)" }}>{fmtDate(e.ts)}</span>
                    {" " + e.dir + " "}
                    <b>{e.subject || "(件名なし)"}</b>{" "}
                    <span className={`status-dot ${sb.dot}`}></span>{sb.text}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="actions">
          <button className="btn secondary" onClick={onClose}>キャンセル</button>
          <button className="btn" disabled={saving} onClick={save}>
            {saving ? <><span className="spinner" /> 保存中…</> : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
