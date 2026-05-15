"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Member, MemberHistory, MemberPurchases, MemberWithdrawSummary } from "@/lib/types";
import { NFT_TYPES, fmtDate, statusInfo, nftBadgeClass, nftLabel } from "@/lib/ui";
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
  const [purchases, setPurchases] = useState<MemberPurchases | null>(null);
  const [withdraws, setWithdraws] = useState<MemberWithdrawSummary | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(isEdit);
  const [section, setSection] = useState<"info" | "purchases" | "withdraws" | "history">("info");

  useEffect(() => {
    if (!isEdit || !email) {
      setForm({ ...EMPTY });
      setHistory(null);
      setPurchases(null);
      setWithdraws(null);
      return;
    }
    setLoading(true);
    Promise.all([
      api.members.history(email).catch(() => null),
      api.members.purchases(email).catch(() => null),
      api.members.withdraws(email).catch(() => null),
    ])
      .then(([h, p, w]) => {
        if (h) { setForm(h.member); setHistory(h); }
        if (p) setPurchases(p);
        if (w) setWithdraws(w);
        if (!h && !p && !w) { notify("読み込みエラー", "error"); onClose(); }
      })
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
          {isEdit && (
            <div className="chip-row" style={{ marginBottom: 16 }}>
              <div className={`chip ${section === "info" ? "active" : ""}`} onClick={() => setSection("info")}>
                基本情報
              </div>
              <div className={`chip ${section === "purchases" ? "active" : ""}`} onClick={() => setSection("purchases")}>
                購入履歴 {purchases?.purchases?.length ? <span className="chip-count">· {purchases.purchases.length}</span> : null}
              </div>
              <div className={`chip ${section === "withdraws" ? "active" : ""}`} onClick={() => setSection("withdraws")}>
                買い取り受取 {withdraws?.count ? <span className="chip-count">· {withdraws.count}</span> : null}
              </div>
              <div className={`chip ${section === "history" ? "active" : ""}`} onClick={() => setSection("history")}>
                やり取り {events.length > 0 ? <span className="chip-count">· {events.length}</span> : null}
              </div>
            </div>
          )}

          {section === "info" && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <div className="field">
                <label>名前</label>
                <input className="input" value={form.name} onChange={(e) => setField("name", e.target.value)} placeholder="山田太郎" />
              </div>
              <div className="field">
                <label>メールアドレス</label>
                <input className="input" type="email" value={form.email} onChange={(e) => setField("email", e.target.value)} placeholder="yamada@example.com" />
              </div>
              <div className="field" style={{ gridColumn: "1 / -1" }}>
                <label>NFT種別（複数の場合はカンマ区切り）</label>
                <input className="input" value={form.nft_type} onChange={(e) => setField("nft_type", e.target.value)} />
                <div className="field-hint">例: 会員権NFT, パチスロホイホイNFT</div>
              </div>
              <div className="field">
                <label>購入日</label>
                <input className="input" type="date" value={form.joined_date} onChange={(e) => setField("joined_date", e.target.value)} />
              </div>
              <div className="field">
                <label>備考</label>
                <input className="input" value={form.notes} onChange={(e) => setField("notes", e.target.value)} placeholder="任意" />
              </div>
            </div>
          )}

          {section === "purchases" && purchases && (
            <PurchasesSection data={purchases} />
          )}

          {section === "withdraws" && withdraws && (
            <WithdrawsSection data={withdraws} />
          )}

          {section === "history" && (
            events.length === 0 ? (
              <p style={{ color: "var(--text-3)", padding: 24, textAlign: "center" }}>過去のやり取りはありません</p>
            ) : (
              <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
                {events.slice(0, 50).map((h, i) => {
                  const s = statusInfo(h.status);
                  return (
                    <div
                      key={i}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "10px 12px", fontSize: 12.5,
                        borderBottom: i < Math.min(events.length, 50) - 1 ? "1px solid var(--border)" : "none",
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
            )
          )}
        </>
      )}
    </Modal>
  );
}

function PurchasesSection({ data }: { data: MemberPurchases }) {
  const summary = data.summary;
  const purchases = data.purchases;

  if (purchases.length === 0) {
    return (
      <p style={{ color: "var(--text-3)", padding: 24, textAlign: "center" }}>
        購入履歴の記録はありません
      </p>
    );
  }

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
        <Stat label="購入件数" value={summary.total_count} />
        <Stat label="投資合計" value={`$${summary.total_jpy.toLocaleString()} USDT`} />
        <Stat label="還元累計" value={`${summary.total_returns_usdt.toFixed(2)} USDT`} />
      </div>

      <div style={{ fontSize: 12, color: "var(--text-2)", fontWeight: 500, marginBottom: 8 }}>
        NFT 種別ごとの集計
      </div>
      <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden", marginBottom: 16 }}>
        {summary.by_nft.map((r, i) => (
          <div
            key={i}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "10px 12px", fontSize: 13,
              borderBottom: i < summary.by_nft.length - 1 ? "1px solid var(--border)" : "none",
              background: i % 2 ? "var(--bg-soft)" : "var(--bg-elev)",
            }}
          >
            <span className={`badge ${nftBadgeClass(r.nft_type)}`}>{nftLabel(r.nft_type)}</span>
            <span style={{ color: "var(--text-3)", fontSize: 12 }}>{r.purchase_count} 回</span>
            {r.total_units != null && (
              <span style={{ color: "var(--text-3)", fontSize: 12 }}>{r.total_units} 口</span>
            )}
            {r.total_jpy != null && r.total_jpy > 0 && (
              <span style={{ color: "var(--text-3)", fontSize: 12 }}>${r.total_jpy.toLocaleString()} USDT</span>
            )}
            {r.total_returns_usdt != null && r.total_returns_usdt > 0 && (
              <span style={{ marginLeft: "auto", color: "var(--success)", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                +{r.total_returns_usdt.toFixed(2)} USDT
              </span>
            )}
            <span style={{ color: "var(--text-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>初: {r.first_purchase || "-"}</span>
          </div>
        ))}
      </div>

      <details>
        <summary>個別の購入レコード（{purchases.length} 件）</summary>
        <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", marginTop: 8, overflow: "hidden", maxHeight: 360, overflowY: "auto" }}>
          {purchases.map((p, i) => (
            <div
              key={p.id}
              style={{
                padding: "10px 12px", fontSize: 12,
                borderBottom: i < purchases.length - 1 ? "1px solid var(--border)" : "none",
                background: i % 2 ? "var(--bg-soft)" : "var(--bg-elev)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span className={`badge ${nftBadgeClass(p.nft_type)}`}>{nftLabel(p.nft_type)}</span>
                <span style={{ color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>{p.purchased_at || "-"}</span>
                {p.amount_jpy != null && p.amount_jpy > 0 && (
                  <span style={{ color: "var(--text-2)" }}>${p.amount_jpy.toLocaleString()} USDT</span>
                )}
                {p.units != null && p.units > 0 && (
                  <span style={{ color: "var(--text-3)" }}>· {p.units} 口</span>
                )}
                {p.returns_usdt != null && p.returns_usdt > 0 && (
                  <span style={{ marginLeft: "auto", color: "var(--success)" }}>還元 {p.returns_usdt.toFixed(2)} USDT</span>
                )}
              </div>
              {(p.transaction_id || p.team || p.notes) && (
                <div style={{ color: "var(--text-4)", fontSize: 11, fontFamily: "var(--font-mono)" }}>
                  {p.team ? `[${p.team}] ` : ""}{p.transaction_id || ""}{p.notes ? ` · ${p.notes}` : ""}
                </div>
              )}
            </div>
          ))}
        </div>
      </details>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div style={{ padding: "12px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--bg-soft)" }}>
      <div style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}

function WithdrawsSection({ data }: { data: MemberWithdrawSummary }) {
  if (data.count === 0) {
    return (
      <p style={{ color: "var(--text-3)", padding: 24, textAlign: "center" }}>
        買い取り資金の受取記録はまだありません。
      </p>
    );
  }
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
        <Stat label="受取回数" value={data.count} />
        <Stat label="受取累計" value={`$${data.total_usdt.toLocaleString()} USDT`} />
      </div>

      <div style={{ fontSize: 12, color: "var(--text-2)", fontWeight: 500, marginBottom: 8 }}>
        nftportal 出金履歴
      </div>
      <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden", maxHeight: 320, overflowY: "auto" }}>
        {data.withdraws.map((w, i) => {
          const statusLabel: Record<number, { text: string; cls: string }> = {
            0: { text: "申請中", cls: "badge-warning" },
            1: { text: "処理中", cls: "badge-info" },
            2: { text: "完了", cls: "badge-success" },
            3: { text: "却下", cls: "badge-danger" },
          };
          const s = statusLabel[w.status ?? -1] || { text: String(w.status ?? "?"), cls: "badge-neutral" };
          return (
            <div
              key={w.id}
              style={{
                padding: "10px 12px", fontSize: 12.5,
                borderBottom: i < data.withdraws.length - 1 ? "1px solid var(--border)" : "none",
                background: i % 2 ? "var(--bg-soft)" : "var(--bg-elev)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ color: "var(--text-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                  {fmtDate(w.requested_at || "")}
                </span>
                <span className={`badge ${s.cls}`}>{s.text}</span>
                <span style={{ marginLeft: "auto", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                  ${w.amount_usdt.toLocaleString()} USDT
                </span>
              </div>
              {w.destination && (
                <div style={{ marginTop: 4, color: "var(--text-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                  → {w.destination.slice(0, 16)}...{w.destination.slice(-8)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
