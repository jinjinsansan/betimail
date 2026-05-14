"use client";
import { useState, useRef } from "react";
import { api, API_BASE } from "@/lib/api";
import type { Member } from "@/lib/types";
import { nftBadgeClass, debounce } from "@/lib/ui";
import MemberEditModal from "../MemberEditModal";

type Props = {
  nftTypes: string[];
  members: Member[];
  notify: (msg: string, err?: boolean) => void;
  onReload: () => void;
};

export default function MembersTab({ nftTypes, members, notify, onReload }: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [nftType, setNftType] = useState(nftTypes[0] || "");
  const [joinedDate, setJoinedDate] = useState(new Date().toISOString().split("T")[0]);
  const [notes, setNotes] = useState("");
  const [adding, setAdding] = useState(false);
  const [filterNft, setFilterNft] = useState("");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const filtered = members.filter((m) => {
    if (filterNft && m.nft_type !== filterNft) return false;
    if (search) {
      const s = search.toLowerCase();
      if (!m.name.toLowerCase().includes(s) && !m.email.toLowerCase().includes(s)) return false;
    }
    return true;
  });

  async function add() {
    if (!name || !email || !nftType) { notify("名前・メール・NFT種別は必須です", true); return; }
    setAdding(true);
    try {
      await api.members.add({ name, email, nft_type: nftType, joined_date: joinedDate, notes });
      notify(`${name} を追加しました`);
      setName(""); setEmail(""); setNotes("");
      onReload();
    } catch (e: any) { notify(e.message, true); }
    finally { setAdding(false); }
  }

  async function remove(email: string) {
    if (!confirm(`${email} を削除しますか？`)) return;
    try {
      await api.members.remove(email);
      notify("削除しました");
      onReload();
    } catch (e: any) { notify(e.message, true); }
  }

  async function importCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const r = await api.members.importCsv(file);
      notify(`${r.added} 件を追加${r.skipped.length ? `（${r.skipped.length} 件スキップ）` : ""}`);
      onReload();
    } catch (err: any) { notify(err.message, true); }
    finally { if (fileRef.current) fileRef.current.value = ""; }
  }

  function exportCsv() {
    // Bearer 認証が必要なので fetch でblob取得してダウンロード
    api.members.list().then(async () => {
      const token = localStorage.getItem("betimail_token");
      const res = await fetch(api.members.exportUrl(), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) { notify("エクスポート失敗", true); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "members.csv"; a.click();
      URL.revokeObjectURL(url);
    });
  }

  return (
    <>
      <div className="card">
        <h2>メンバー追加
          <div className="actions">
            <label className="btn secondary small" style={{ margin: 0, cursor: "pointer" }}>
              📥 CSV取り込み
              <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={importCsv} />
            </label>
            <button className="btn secondary small" onClick={exportCsv}>📤 CSV書き出し</button>
          </div>
        </h2>
        <div className="flex-row">
          <div>
            <label>名前</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="山田太郎" />
          </div>
          <div>
            <label>メールアドレス</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="yamada@example.com" />
          </div>
        </div>
        <div className="flex-row" style={{ marginTop: 0 }}>
          <div>
            <label>NFT種別</label>
            <select value={nftType} onChange={(e) => setNftType(e.target.value)}>
              {nftTypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label>購入日</label>
            <input type="date" value={joinedDate} onChange={(e) => setJoinedDate(e.target.value)} />
          </div>
          <div>
            <label>備考</label>
            <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="任意" />
          </div>
        </div>
        <button className="btn" style={{ marginTop: 16 }} disabled={adding} onClick={add}>
          {adding ? <><span className="spinner" /> 追加中…</> : "追加"}
        </button>
      </div>

      <div className="card">
        <h2>メンバー一覧</h2>
        <div style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select value={filterNft} onChange={(e) => setFilterNft(e.target.value)} style={{ width: 220 }}>
            <option value="">-- すべてのNFT種別 --</option>
            {nftTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="名前・メールで検索" style={{ width: 240 }} />
          <span style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>{filtered.length} 名</span>
        </div>
        <table>
          <thead><tr><th>名前</th><th>メールアドレス</th><th>NFT種別</th><th>購入日</th><th>備考</th><th></th></tr></thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={6} className="placeholder">メンバーが見つかりません</td></tr>
            ) : filtered.map((m) => (
              <tr key={m.email}>
                <td>{m.name}</td>
                <td>{m.email}</td>
                <td><span className={`badge ${nftBadgeClass(m.nft_type)}`}>{m.nft_type || "不明"}</span></td>
                <td>{m.joined_date || "-"}</td>
                <td>{m.notes || "-"}</td>
                <td>
                  <button className="btn small secondary" onClick={() => setEditing(m.email)}>編集</button>
                  <button className="btn small danger" style={{ marginLeft: 6 }} onClick={() => remove(m.email)}>削除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <MemberEditModal
          email={editing}
          nftTypes={nftTypes}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); onReload(); }}
          notify={notify}
        />
      )}
    </>
  );
}
