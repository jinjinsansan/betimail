"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Member } from "@/lib/types";
import { NFT_TYPES, nftBadgeClass, nftLabel, memberInitial } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Empty, Pager } from "../common";
import MemberEditModal from "../MemberEditModal";

type Props = {
  members: Member[];
  notify: (msg: string, type?: "success" | "error" | "info") => void;
  onReload: () => void;
};

const PAGE = 12;

export default function MembersTab({ members, notify, onReload }: Props) {
  const [filterNft, setFilterNft] = useState<string>("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    let list = members;
    if (filterNft) {
      list = list.filter((m) =>
        (m.nft_type || "")
          .split(",")
          .map((t) => t.trim())
          .includes(filterNft)
      );
    }
    if (search) {
      const s = search.toLowerCase();
      list = list.filter((m) =>
        m.name.toLowerCase().includes(s) || m.email.toLowerCase().includes(s));
    }
    return list;
  }, [members, filterNft, search]);

  useEffect(() => { setPage(0); }, [filterNft, search]);

  const pageCount = Math.ceil(filtered.length / PAGE);
  const slice = filtered.slice(page * PAGE, (page + 1) * PAGE);

  async function remove(m: Member) {
    if (!confirm(`${m.email} を削除しますか？`)) return;
    try {
      await api.members.remove(m.email);
      notify(`${m.name} を削除しました`);
      onReload();
    } catch (e: any) { notify(e.message, "error"); }
  }

  async function importCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const r = await api.members.importCsv(file);
      notify(`${r.added} 件を追加${r.skipped.length ? `（${r.skipped.length} 件スキップ）` : ""}`);
      onReload();
    } catch (err: any) { notify(err.message, "error"); }
    finally { if (fileRef.current) fileRef.current.value = ""; }
  }

  async function exportCsv() {
    try {
      const token = localStorage.getItem("betimail_token");
      const res = await fetch(api.members.exportUrl(), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error("エクスポート失敗");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "members.csv"; a.click();
      URL.revokeObjectURL(url);
      notify("members.csv を書き出しました");
    } catch (e: any) { notify(e.message, "error"); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">メンバー管理</h1>
          <div className="page-sub">全 {members.length} 名のメンバー情報を管理。CSV インポート / エクスポート対応。</div>
        </div>
        <div className="page-head-actions">
          <label className="btn ghost" style={{ cursor: "pointer", margin: 0 }}>
            <I.Upload /> CSV 取り込み
            <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={importCsv} />
          </label>
          <button className="btn ghost" onClick={exportCsv}><I.Download /> 書き出し</button>
          <button className="btn primary" onClick={() => setShowAdd(true)}><I.Plus /> メンバー追加</button>
        </div>
      </div>

      <div className="card">
        <div className="filter-bar">
          <div className="search-wrap">
            <I.Search />
            <input className="input" placeholder="名前・メールで検索…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="chip-row">
            <div className={`chip ${filterNft === "" ? "active" : ""}`} onClick={() => setFilterNft("")}>すべて</div>
            {NFT_TYPES.map((t) => (
              <div key={t} className={`chip ${filterNft === t ? "active" : ""}`} onClick={() => setFilterNft(t)}>
                {nftLabel(t)}
              </div>
            ))}
          </div>
          <span className="count">{filtered.length} 名</span>
        </div>

        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>名前</th>
                <th>メールアドレス</th>
                <th>NFT種別</th>
                <th>購入日</th>
                <th>備考</th>
                <th style={{ width: 100 }}></th>
              </tr>
            </thead>
            <tbody>
              {slice.length === 0 ? (
                <tr><td colSpan={6}><Empty icon={<I.Users />} title="該当するメンバーがいません" /></td></tr>
              ) : slice.map((m) => (
                <tr key={m.email}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div className="avatar" style={{ width: 26, height: 26, fontSize: 11, background: "var(--bg-inset)", color: "var(--text-2)" }}>
                        {memberInitial(m)}
                      </div>
                      <b>{m.name}</b>
                    </div>
                  </td>
                  <td>{m.email}</td>
                  <td><span className={`badge ${nftBadgeClass(m.nft_type)}`}>{nftLabel(m.nft_type)}</span></td>
                  <td><span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{m.joined_date || "-"}</span></td>
                  <td>{m.notes ? <span className="badge badge-neutral">{m.notes}</span> : <span style={{ color: "var(--text-4)" }}>—</span>}</td>
                  <td>
                    <div className="row-actions">
                      <button className="btn ghost sm" onClick={() => setEditing(m.email)}><I.Edit /></button>
                      <button className="btn ghost sm" style={{ color: "var(--danger)" }} onClick={() => remove(m)}><I.Trash /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 12, color: "var(--text-3)" }}>
            {filtered.length === 0 ? 0 : page * PAGE + 1}–{Math.min((page + 1) * PAGE, filtered.length)} / {filtered.length}
          </span>
          <Pager page={page} pageCount={pageCount} onChange={setPage} />
        </div>
      </div>

      {(showAdd || editing) && (
        <MemberEditModal
          email={editing}
          mode={editing ? "edit" : "add"}
          onClose={() => { setShowAdd(false); setEditing(null); }}
          onSaved={() => { setShowAdd(false); setEditing(null); onReload(); }}
          notify={notify}
        />
      )}
    </>
  );
}
