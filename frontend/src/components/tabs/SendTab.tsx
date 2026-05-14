"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Member, Template, BulkJob } from "@/lib/types";
import { debounce } from "@/lib/ui";

type Props = {
  nftTypes: string[];
  members: Member[];
  templates: Template[];
  onReload: () => void;
  notify: (msg: string, err?: boolean) => void;
  onJump: (tab: string) => void;
};

export default function SendTab({ nftTypes, members, templates, onReload, notify }: Props) {
  const [selectedNfts, setSelectedNfts] = useState<string[]>([]);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState("");
  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  const [job, setJob] = useState<BulkJob | null>(null);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    nftTypes.forEach((t) => (c[t] = 0));
    members.forEach((m) => { if (c[m.nft_type] !== undefined) c[m.nft_type]++; });
    return c;
  }, [nftTypes, members]);

  // body 変更時にプレビュー更新
  useEffect(() => {
    if (!body.trim()) {
      setPreview("本文を入力するとプレビュー表示されます。");
      return;
    }
    const fn = debounce(async () => {
      try {
        const r = await api.preview(body);
        setPreview(r.rendered);
      } catch (e: any) {
        setPreview(`⚠️ ${e.message}`);
      }
    }, 400);
    fn();
  }, [body]);

  function toggleNft(t: string) {
    setSelectedNfts((cur) => cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]);
  }

  function calcPreviewCount() {
    if (selectedNfts.length === 0) {
      setPreviewCount(members.length);
    } else {
      setPreviewCount(members.filter((m) => selectedNfts.includes(m.nft_type)).length);
    }
  }

  async function pollJob(jobId: number) {
    const tick = async () => {
      try {
        const j = await api.send.job(jobId);
        setJob(j);
        if (j.status === "done") {
          clearInterval(handle);
          onReload();
        }
      } catch {
        clearInterval(handle);
      }
    };
    const handle = setInterval(tick, 1500);
    tick();
  }

  async function send() {
    if (!subject.trim() || !body.trim()) {
      notify("件名と本文を入力してください", true);
      return;
    }
    const count = selectedNfts.length === 0 ? members.length : members.filter((m) => selectedNfts.includes(m.nft_type)).length;
    if (!confirm(`${count} 名にメールを送信します。よろしいですか？`)) return;
    setSending(true);
    try {
      const r = await api.send.bulk({ nft_types: selectedNfts, subject, body });
      notify(`送信開始: ${r.count}名 (ジョブID ${r.job_id})`);
      setJob({ id: r.job_id, total: r.count, sent: 0, failed: 0, status: "running" } as BulkJob);
      pollJob(r.job_id);
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setSending(false);
    }
  }

  async function saveAsTemplate() {
    if (!subject.trim() || !body.trim()) { notify("件名と本文を入力してください", true); return; }
    const name = prompt("テンプレート名:");
    if (!name) return;
    try {
      await api.templates.upsert(name, subject, body);
      notify("テンプレートを保存しました");
      onReload();
    } catch (e: any) { notify(e.message, true); }
  }

  function applyTemplate(id: number) {
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    setSubject(t.subject);
    setBody(t.body);
    notify(`「${t.name}」を適用しました`);
  }

  const jobPct = job && job.total > 0 ? Math.round(((job.sent + job.failed) / job.total) * 100) : 0;

  return (
    <>
      <div className="stats-row">
        <div className="stat"><div className="num">{members.length}</div><div className="lbl">総メンバー数</div></div>
        {nftTypes.map((t) => (
          <div className="stat" key={t}><div className="num">{counts[t] ?? 0}</div><div className="lbl">{t}</div></div>
        ))}
      </div>

      <div className="card">
        <h2>メール送信
          <div className="actions">
            <select onChange={(e) => { if (e.target.value) { applyTemplate(parseInt(e.target.value)); e.target.value = ""; } }}>
              <option value="">テンプレートから適用…</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
        </h2>

        <label>送信対象 NFT種別（未選択で全員に送信）</label>
        <div className="nft-checkboxes">
          {nftTypes.map((t) => (
            <label key={t}>
              <input type="checkbox" checked={selectedNfts.includes(t)} onChange={() => { toggleNft(t); setPreviewCount(null); }} />
              {t}
            </label>
          ))}
        </div>

        <label>件名</label>
        <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="例: 【重要】コミュニティからのお知らせ" />

        <label>本文</label>
        <p className="hint">※ {`{name}`}・{`{nft_type}`}・{`{email}`} は自動的にメンバー情報に置換されます</p>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={"{name} 様\n\nいつもコミュニティをご利用いただきありがとうございます。\n{nft_type} オーナーの皆様へお知らせです。\n\n...\n\n運営チーム"}
        />

        <details style={{ marginTop: 14 }}>
          <summary>プレビュー（メンバー1人目に対する文面）</summary>
          <div className="preview-pane" style={{ marginTop: 10 }}>{preview}</div>
        </details>

        <div style={{ marginTop: 16, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn" disabled={sending} onClick={send}>
            {sending ? <><span className="spinner" /> 送信中…</> : "📤 送信する"}
          </button>
          <button className="btn secondary" onClick={calcPreviewCount}>対象人数を確認</button>
          <button className="btn secondary" onClick={saveAsTemplate}>💾 テンプレート保存</button>
          {previewCount != null && <span style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>対象: {previewCount}名</span>}
        </div>

        {job && (
          <div className="result-box">
            <div className="result-item">ジョブID <b>{job.id}</b> · 進捗 {job.sent + job.failed}/{job.total} ({jobPct}%)</div>
            <div className="result-item">✅ 送信成功: {job.sent} / ❌ 失敗: {job.failed} / 状態: {job.status}</div>
            <div className="progress-bar"><div style={{ width: `${jobPct}%` }} /></div>
          </div>
        )}
      </div>
    </>
  );
}
