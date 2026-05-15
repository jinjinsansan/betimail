"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Member, Template, BulkJob } from "@/lib/types";
import { NFT_TYPES, nftLabel, debounce, nftBadgeClass, uniqueInboxCount } from "@/lib/ui";
import { I } from "@/lib/icons";
import { Modal } from "../common";

type Props = {
  members: Member[];
  templates: Template[];
  onReload: () => void;
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

type SegmentKey = "lucky_only" | "lucky_and_special";

const SEGMENT_LABELS: Record<SegmentKey, string> = {
  lucky_only: "ラッキー単独",
  lucky_and_special: "ラッキー+スペシャル",
};

function memberNftTypes(m: Member): string[] {
  return (m.nft_type || "").split(",").map((t) => t.trim()).filter(Boolean);
}

export default function SendTab({ members, templates, onReload, notify }: Props) {
  const [selectedNfts, setSelectedNfts] = useState<string[]>([]);
  const [segment, setSegment] = useState<SegmentKey | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState("本文を入力するとプレビュー表示されます。");
  const [sending, setSending] = useState(false);
  const [job, setJob] = useState<BulkJob | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  // NFT 保有数（カンマ区切り対応）
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    NFT_TYPES.forEach((t) => (c[t] = 0));
    members.forEach((m) => {
      memberNftTypes(m).forEach((t) => {
        if (c[t] != null) c[t]++;
      });
    });
    return c;
  }, [members]);

  // セグメント別人数
  const segmentCounts = useMemo(() => {
    let lucky_only = 0, lucky_and_special = 0;
    for (const m of members) {
      const types = new Set(memberNftTypes(m));
      const hasLucky = types.has("ラッキーマスタードNFT");
      const hasSpecial = types.has("スペシャルマスタードNFT");
      if (hasLucky && !hasSpecial) lucky_only++;
      if (hasLucky && hasSpecial) lucky_and_special++;
    }
    return { lucky_only, lucky_and_special };
  }, [members]);

  // 送信対象計算
  const target = useMemo(() => {
    if (segment === "lucky_only") {
      return members.filter((m) => {
        const t = new Set(memberNftTypes(m));
        return t.has("ラッキーマスタードNFT") && !t.has("スペシャルマスタードNFT");
      });
    }
    if (segment === "lucky_and_special") {
      return members.filter((m) => {
        const t = new Set(memberNftTypes(m));
        return t.has("ラッキーマスタードNFT") && t.has("スペシャルマスタードNFT");
      });
    }
    if (selectedNfts.length === 0) return members;
    return members.filter((m) => {
      const t = memberNftTypes(m);
      return selectedNfts.some((s) => t.includes(s));
    });
  }, [members, segment, selectedNfts]);

  // Gmail エイリアスを正規化して実際に届く受信箱数を算出
  const uniqueInboxes = useMemo(() => uniqueInboxCount(target.map((m) => m.email)), [target]);
  const dedupedAway = target.length - uniqueInboxes;

  function toggleNft(t: string) {
    setSegment(null); // セグメント選択を解除（NFT種別が優先）
    setSelectedNfts((cur) => cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]);
  }

  function selectSegment(s: SegmentKey) {
    setSelectedNfts([]); // NFT選択を解除
    setSegment((cur) => (cur === s ? null : s));
  }

  function applyTemplate(id: number) {
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    setSubject(t.subject);
    setBody(t.body);
    notify(`「${t.name}」を適用しました`);
  }

  useEffect(() => {
    if (!body.trim()) {
      setPreview("本文を入力するとプレビュー表示されます。");
      return;
    }
    const fn = debounce(async () => {
      try {
        const r = await api.preview(body, target[0] || members[0]);
        setPreview(r.rendered);
      } catch (e: any) {
        setPreview(`⚠️ ${e.message}`);
      }
    }, 400);
    fn();
  }, [body, target.length, members.length]);

  async function pollJob(jobId: number) {
    const tick = async () => {
      try {
        const j = await api.send.job(jobId);
        setJob(j);
        if (j.status === "done") {
          clearInterval(handle);
          onReload();
          notify(`${j.sent} 名に送信完了${j.failed > 0 ? ` (失敗 ${j.failed})` : ""}`, j.failed > 0 ? "error" : "success");
        }
      } catch {
        clearInterval(handle);
      }
    };
    const handle = setInterval(tick, 1500);
    tick();
  }

  function send() {
    if (!subject.trim() || !body.trim()) {
      notify("件名と本文を入力してください", "error");
      return;
    }
    setShowConfirm(true);
  }

  async function confirmSend() {
    setShowConfirm(false);
    setSending(true);
    try {
      const r = await api.send.bulk({
        nft_types: selectedNfts,
        segment: segment || null,
        confirm_all: !segment && selectedNfts.length === 0,
        subject, body,
      });
      notify(`送信開始: ${r.count}名 (ジョブID ${r.job_id})`);
      setJob({ id: r.job_id, total: r.count, sent: 0, failed: 0, status: "running" } as BulkJob);
      pollJob(r.job_id);
    } catch (e: any) {
      notify(e.message, "error");
    } finally {
      setSending(false);
    }
  }

  async function saveAsTemplate() {
    if (!subject.trim() || !body.trim()) {
      notify("件名と本文を入力してください", "error");
      return;
    }
    const name = prompt("テンプレート名:");
    if (!name) return;
    try {
      await api.templates.upsert(name, subject, body);
      notify("テンプレートとして保存しました");
      onReload();
    } catch (e: any) { notify(e.message, "error"); }
  }

  function clearForm() {
    setSubject(""); setBody(""); setSelectedNfts([]);
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">メール送信</h1>
          <div className="page-sub">メンバーへ一斉メールを配信します。NFT 種別でフィルタ可能。</div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>新規メール</h3>
          <div className="card-head-actions">
            <select
              className="select"
              style={{ width: 200 }}
              onChange={(e) => { if (e.target.value) { applyTemplate(parseInt(e.target.value)); e.target.value = ""; } }}
              defaultValue=""
            >
              <option value="">テンプレートから挿入…</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
        </div>

        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div className="field">
            <label>送信対象 — NFT種別</label>
            <div className="chip-row">
              <div
                className={`chip ${selectedNfts.length === 0 && !segment ? "active" : ""}`}
                onClick={() => { setSelectedNfts([]); setSegment(null); }}
              >
                すべて <span className="chip-count">· {members.length}</span>
              </div>
              {NFT_TYPES.map((t) => (
                <div key={t} className={`chip ${selectedNfts.includes(t) ? "active" : ""}`} onClick={() => toggleNft(t)}>
                  {nftLabel(t)} <span className="chip-count">· {counts[t]}</span>
                </div>
              ))}
            </div>
            <div className="field-hint">未選択は全員に送信。複数選択で OR フィルタ。</div>
          </div>

          <div className="field">
            <label>送信対象 — セグメント（NFT 種別と排他）</label>
            <div className="chip-row">
              <div
                className={`chip ${segment === "lucky_only" ? "active" : ""}`}
                onClick={() => selectSegment("lucky_only")}
              >
                {SEGMENT_LABELS.lucky_only} <span className="chip-count">· {segmentCounts.lucky_only}</span>
              </div>
              <div
                className={`chip ${segment === "lucky_and_special" ? "active" : ""}`}
                onClick={() => selectSegment("lucky_and_special")}
              >
                {SEGMENT_LABELS.lucky_and_special} <span className="chip-count">· {segmentCounts.lucky_and_special}</span>
              </div>
            </div>
            <div className="field-hint">
              「ラッキー単独」= ラッキー保有かつスペシャル非保有 / 「ラッキー+スペシャル」= 両方保有。
            </div>
          </div>

          <div className="field">
            <label>件名</label>
            <input
              className="input"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="例: 【重要】コミュニティからのお知らせ"
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="field">
              <label>本文</label>
              <textarea
                className="textarea"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={"{name} 様\n\nいつもコミュニティをご利用いただきありがとうございます。\n{nft_type} オーナーの皆様へお知らせです。\n\n…\n\n運営チーム"}
              />
              <div className="field-hint">
                プレースホルダ:
                <span className="kbd">{"{name}"}</span>
                <span className="kbd" style={{ marginLeft: 4 }}>{"{nft_type}"}</span>
                <span className="kbd" style={{ marginLeft: 4 }}>{"{email}"}</span>
              </div>
            </div>
            <div className="field">
              <label>
                プレビュー <span style={{ color: "var(--text-4)", fontWeight: 400 }}>({target[0]?.name || "—"} に対する文面)</span>
              </label>
              <div className="preview-box" style={{ minHeight: 140, height: "100%" }}>{preview}</div>
            </div>
          </div>
        </div>

        <div style={{ padding: "14px 20px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10, background: "var(--bg-soft)", flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "var(--text-2)" }}>
            <b style={{ color: "var(--text)", fontVariantNumeric: "tabular-nums" }}>{target.length} 名</b>
            {dedupedAway > 0 && (
              <>
                {" → "}
                <b style={{ color: "var(--accent)", fontVariantNumeric: "tabular-nums" }}>{uniqueInboxes} 通</b>
                <span style={{ color: "var(--text-3)", fontSize: 12, marginLeft: 6 }}>
                  （{dedupedAway} 件のエイリアス重複を統合）
                </span>
              </>
            )}
            {" に送信"}
          </span>
          <button className="btn ghost sm" onClick={saveAsTemplate}><I.Save /> テンプレート保存</button>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <button className="btn ghost" onClick={clearForm}>クリア</button>
            <button className="btn primary" disabled={sending} onClick={send}>
              {sending ? <><span className="spinner" /> 送信中…</> : <><I.Send /> 送信する</>}
            </button>
          </div>
        </div>

        {job && (
          <div style={{ padding: "16px 20px", borderTop: "1px solid var(--border)", background: "var(--bg-elev)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 6 }}>
              <span className="badge badge-info">ジョブ #{job.id}</span>
              <span style={{ color: "var(--text-2)" }}>{job.sent + job.failed} / {job.total} 配信</span>
              {job.failed > 0 && <span style={{ color: "var(--danger)" }}>失敗 {job.failed}</span>}
              <span style={{ marginLeft: "auto", color: "var(--text-3)" }}>
                {job.status === "done" ? "完了" : "実行中…"}
              </span>
            </div>
            <div className="progress">
              <div style={{ width: `${job.total ? Math.round(((job.sent + job.failed) / job.total) * 100) : 0}%` }} />
            </div>
          </div>
        )}
      </div>

      <Modal
        open={showConfirm}
        onClose={() => setShowConfirm(false)}
        title="送信確認"
        footer={
          <>
            <button className="btn ghost" onClick={() => setShowConfirm(false)}>キャンセル</button>
            <button className="btn primary" onClick={confirmSend}><I.Send /> 送信する</button>
          </>
        }
      >
        <div style={{ fontSize: 14, lineHeight: 1.7 }}>
          <p>
            以下の内容で <b>{target.length} 名</b> 中、
            実際に届く <b style={{ color: "var(--accent)" }}>{uniqueInboxes} 通</b> に送信します。
            {dedupedAway > 0 && (
              <span style={{ color: "var(--text-3)", fontSize: 13 }}>
                <br />（同一受信箱への {dedupedAway} 件のエイリアス重複は統合されます）
              </span>
            )}
          </p>
          <div style={{ marginTop: 14, padding: 14, background: "var(--bg-soft)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 4 }}>件名</div>
            <b>{subject || "(未入力)"}</b>
            <div style={{ marginTop: 10, fontSize: 12, color: "var(--text-3)" }}>対象</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
              {(selectedNfts.length === 0 ? (NFT_TYPES as readonly string[]) : selectedNfts).map((t) => (
                <span key={t} className={`badge ${nftBadgeClass(t)}`}>{nftLabel(t)} · {counts[t]}</span>
              ))}
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
}
