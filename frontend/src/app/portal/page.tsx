"use client";
import { useEffect, useRef, useState, FormEvent } from "react";
import {
  portalApi, getPortalToken, setPortalToken, clearPortalToken,
  fmtUsdt, fmtDateShort, PORTAL_NFT_LABELS,
  BUYBACK_STATUS_LABELS, WITHDRAWAL_STATUS_LABELS, LEGACY_WD_STATUS_LABELS,
  type PortalDashboard, type PortalAsset,
} from "@/lib/portal";
import s from "./page.module.css";

type Stage = "loading" | "email" | "code" | "dashboard";
const PAGE_SIZE = 6;

export default function Portal() {
  const [stage, setStage] = useState<Stage>("loading");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [expiresIn, setExpiresIn] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resent, setResent] = useState(false);
  const [dash, setDash] = useState<PortalDashboard | null>(null);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!getPortalToken()) { if (alive) setStage("email"); return; }
      try {
        const d = await portalApi.me();
        if (alive) { setDash(d); setStage("dashboard"); }
      } catch {
        clearPortalToken();
        if (alive) setStage("email");
      }
    })();
    return () => { alive = false; };
  }, []);

  async function submitEmail(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const t = email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t)) { setError("メールアドレスを正しく入力してください"); return; }
    setBusy(true);
    try {
      const r = await portalApi.login(t);
      if (r.verification_required) {
        setMaskedEmail(r.masked_email || t);
        setExpiresIn(r.expires_in || null);
        setStage("code");
        setTimeout(() => codeRef.current?.focus(), 60);
      } else {
        setError("このメールアドレスは会員として登録されていません。NFT購入時（ポータルサイト登録時）のメールアドレスをご確認ください。");
      }
    } catch (e: any) {
      setError(e?.status === 429 ? "リクエストが多すぎます。少し時間をおいてください。"
        : e?.message || "送信に失敗しました。時間をおいて再度お試しください。");
    } finally { setBusy(false); }
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const c = code.trim();
    if (!c) { setError("ログインコードを入力してください"); return; }
    setBusy(true);
    try {
      const r = await portalApi.verify(email.trim().toLowerCase(), c);
      setPortalToken(r.token);
      setDash(r.dashboard);
      setStage("dashboard");
      setCode("");
    } catch (e: any) {
      setError(e?.message || "コードが無効または期限切れです。");
    } finally { setBusy(false); }
  }

  async function resend() {
    setError(null); setResent(false); setBusy(true);
    try {
      const r = await portalApi.login(email.trim().toLowerCase());
      if (r.verification_required) {
        setMaskedEmail(r.masked_email || email);
        setExpiresIn(r.expires_in || null);
        setResent(true);
      }
    } catch (e: any) {
      setError(e?.status === 429 ? "再送は少し時間をおいてください。" : e?.message || "再送に失敗しました。");
    } finally { setBusy(false); }
  }

  function logout() {
    clearPortalToken();
    setDash(null); setEmail(""); setCode(""); setError(null); setResent(false);
    setStage("email");
  }

  const isLogin = stage === "email" || stage === "code";

  return (
    <div className={s.page} style={{ display: "flex", flexDirection: "column" }}>
      <div className={s.shell}>
        <header className={s.topbar}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Mark size={36} />
            <div style={{ lineHeight: 1.16 }}>
              <div className={s.serif} style={{ fontSize: 16, fontWeight: 700, letterSpacing: ".04em" }}>betiダッシュボード</div>
              <div style={{ fontSize: 10, color: "var(--gold-deep)", fontWeight: 700, letterSpacing: ".22em" }}>MEMBER PORTAL</div>
            </div>
          </div>
          {stage === "dashboard" && (
            <button className={s.logout} onClick={logout} aria-label="ログアウト">ログアウト</button>
          )}
        </header>

        <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          {stage === "loading" && (
            <div style={{ textAlign: "center", padding: "70px 0", color: "var(--sub)" }}>
              <span className={s.spinnerDark} /> &nbsp;読み込み中…
            </div>
          )}

          {isLogin && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", padding: "24px 22px 40px", maxWidth: 430, width: "100%", margin: "0 auto" }}>
              <div style={{ textAlign: "center", marginBottom: 30 }}>
                <Mark size={66} ringed />
                <div style={{ fontSize: 10.5, color: "var(--gold-deep)", fontWeight: 700, letterSpacing: ".24em", margin: "20px 0 10px" }}>BETI DASHBOARD</div>
                <h1 className={s.serif} style={{ margin: "0 0 10px", fontSize: 25, fontWeight: 700, letterSpacing: ".02em" }}>会員ページにログイン</h1>
                <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.8, color: "var(--sub)" }}>
                  ポータルサイトにご登録いただいた<br />メールアドレスでログインできます。
                </p>
              </div>

              <div style={{ position: "relative", background: "var(--card)", border: "1px solid var(--line)", borderRadius: 24, padding: "26px 22px", boxShadow: "var(--sh)" }}>
                <div aria-hidden style={{ position: "absolute", top: 0, left: 32, right: 32, height: 2, background: "linear-gradient(90deg,transparent,var(--gold),transparent)", opacity: .7 }} />

                {stage === "email" && (
                  <form onSubmit={submitEmail}>
                    <label htmlFor="pt-email" style={lblStyle}>メールアドレス</label>
                    <input id="pt-email" className={s.input} type="email" inputMode="email" autoComplete="email"
                      placeholder="example@gmail.com" value={email}
                      onChange={(e) => { setEmail(e.target.value); setError(null); }} autoFocus />
                    <div style={{ fontSize: 12, color: "var(--sub)", marginTop: 10, lineHeight: 1.6 }}>
                      ご登録のメールアドレスにログインコードをお送りします。
                    </div>
                    {error && <ErrorBox msg={error} />}
                    <button type="submit" className={s.btn} style={{ marginTop: 18 }} disabled={busy}>
                      {busy && <span className={s.spinner} />}{busy ? "送信中…" : "ログインコードを送る"}
                    </button>
                  </form>
                )}

                {stage === "code" && (
                  <form onSubmit={submitCode}>
                    <div style={{ fontSize: 12.5, color: "var(--sub)", lineHeight: 1.75, background: "var(--soft)", border: "1px solid var(--line)", borderRadius: 13, padding: "12px 14px", marginBottom: 20 }}>
                      <strong style={{ color: "var(--ink)", fontWeight: 700 }}>{maskedEmail}</strong> 宛にログインコードを送信しました。
                      {expiresIn ? `（有効期限 約${Math.max(1, Math.floor(expiresIn / 60))}分）` : ""}
                    </div>
                    <label htmlFor="pt-code" style={lblStyle}>ログインコード（6桁）</label>
                    <input id="pt-code" ref={codeRef} className={`${s.input} ${s.codeInput}`} type="text"
                      inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="••••••"
                      value={code} onChange={(e) => { setCode(e.target.value.replace(/\D/g, "")); setError(null); }} />
                    {resent && <div style={{ fontSize: 12, color: "var(--pos)", marginTop: 11, display: "flex", gap: 7, alignItems: "center" }}><span aria-hidden>✓</span>コードを再送しました。</div>}
                    {error && <ErrorBox msg={error} />}
                    <button type="submit" className={s.btn} style={{ marginTop: 18 }} disabled={busy}>
                      {busy && <span className={s.spinner} />}{busy ? "確認中…" : "ログイン"}
                    </button>
                    <button type="button" className={s.btnGhost} style={{ marginTop: 11 }} onClick={resend} disabled={busy}>
                      コードを再送する
                    </button>
                  </form>
                )}
              </div>
              <p style={{ textAlign: "center", fontSize: 11, color: "var(--faint)", margin: "24px 0 0", letterSpacing: ".06em" }}>© 2026 beti コミュニティ運営</p>
            </div>
          )}

          {stage === "dashboard" && dash && <Dashboard dash={dash} onUpdate={setDash} />}
        </main>
      </div>
    </div>
  );
}

const lblStyle: React.CSSProperties = {
  display: "block", fontSize: 12, fontWeight: 700, color: "var(--gold-deep)",
  marginBottom: 9, letterSpacing: ".06em",
};

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div role="alert" style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12.5, color: "#B4452F", background: "#FBEDE9", border: "1px solid #F3D6CE", borderRadius: 11, padding: "11px 13px", marginTop: 15, lineHeight: 1.65 }}>
      <span aria-hidden style={{ flex: "none", fontWeight: 700 }}>⚠</span><span>{msg}</span>
    </div>
  );
}

function Mark({ size, ringed }: { size: number; ringed?: boolean }) {
  // 盾をかたどった紺×薄金のマーク（資産を守るダッシュボードの象徴）
  return (
    <svg viewBox="0 0 64 64" style={{ width: size, height: size, display: "block", margin: ringed ? "0 auto" : undefined, flex: "none" }} aria-hidden>
      {ringed && <circle cx="32" cy="32" r="30" fill="var(--card)" stroke="var(--gold)" strokeWidth="1.1" />}
      {!ringed && <circle cx="32" cy="32" r="29" fill="none" stroke="var(--gold)" strokeWidth="1.3" />}
      <path d="M32 14 L46 20 V32 C46 41 40.5 47.5 32 51 C23.5 47.5 18 41 18 32 V20 Z"
        fill="var(--navy)" stroke="var(--gold)" strokeWidth="1.2" />
      <path d="M25.5 32.5 L30 37 L39 26.5" fill="none" stroke="var(--gold2)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ================= ダッシュボード ================= */

function Dashboard({ dash, onUpdate }: { dash: PortalDashboard; onUpdate: (d: PortalDashboard) => void }) {
  const hoihoi = dash.assets.find((a) => a.nft_type === "HOIHOI");
  const hoihoiBuyback = dash.buybacks.find((b) => b.nft_type === "HOIHOI");

  return (
    <div style={{ padding: "20px 18px 44px", display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ marginTop: 4 }}>
        <div style={{ fontSize: 10.5, color: "var(--gold-deep)", fontWeight: 700, letterSpacing: ".22em" }}>MEMBER DASHBOARD</div>
        <div className={s.serif} style={{ fontSize: 23, fontWeight: 700, letterSpacing: ".02em", marginTop: 5 }}>
          {dash.name ? `${dash.name} 様` : "ようこそ"}
        </div>
      </div>

      {/* HERO balance（紺グラデ + 薄金） */}
      <div style={{ position: "relative", borderRadius: 26, padding: "28px 26px 24px", overflow: "hidden", background: "linear-gradient(158deg,var(--navy2),var(--navy))", boxShadow: "0 24px 50px -24px rgba(29,44,79,.55), inset 0 1px 0 rgba(255,255,255,.08)" }}>
        <div aria-hidden style={{ position: "absolute", inset: 0, background: "radial-gradient(90% 70% at 88% -10%, rgba(216,188,118,.22), transparent 60%)" }} />
        <div aria-hidden style={{ position: "absolute", top: 0, left: 26, right: 26, height: 1.5, background: "linear-gradient(90deg,transparent,var(--gold2),transparent)", opacity: .8 }} />
        <div style={{ position: "relative" }}>
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".16em", color: "var(--gold2)" }}>CURRENT BALANCE</div>
          <div style={{ fontSize: 12, color: "var(--navysub)", marginTop: 6 }}>現在の残高 (USDT)</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginTop: 14, color: "var(--navyink)" }}>
            <span className={s.serif} style={{ fontSize: 26, fontWeight: 600, color: "var(--gold2)" }}>$</span>
            <span className={s.serif} style={{ fontSize: 50, fontWeight: 700, lineHeight: 1, letterSpacing: "-.01em", fontVariantNumeric: "tabular-nums" }}>{fmtUsdt(dash.balance)}</span>
          </div>
          <div aria-hidden style={{ height: 1, background: "linear-gradient(90deg,rgba(216,188,118,.4),transparent)", margin: "18px 0 0" }} />
          <div style={{ fontSize: 11.5, color: "var(--navysub)", marginTop: 13, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--gold2)", display: "inline-block" }} />
            累計受取額 ${fmtUsdt(dash.cumulative_reward)}
          </div>
        </div>
      </div>

      {/* NFT 資産 */}
      <Section title="保有NFT資産">
        {dash.assets.length === 0 ? (
          <EmptyNote text="NFT資産の記録が見つかりません。お心当たりがある場合は support@betimail.uk までお問い合わせください。" />
        ) : dash.assets.map((a) => (
          <AssetCard key={a.nft_type} asset={a}
            buyback={dash.buybacks.find((b) => b.nft_type === a.nft_type)}
            onUpdate={onUpdate} />
        ))}
      </Section>

      {/* 買い取り / 継続（HOIHOI 保有者のみ） */}
      {hoihoi && (
        <BuybackPanel asset={hoihoi} buyback={hoihoiBuyback} onUpdate={onUpdate} />
      )}

      {/* 出金申請 */}
      <WithdrawPanel dash={dash} onUpdate={onUpdate} />

      {/* 報酬履歴 */}
      <HistoryList dash={dash} />

      {/* 過去の出金履歴（旧ポータル分含む） */}
      <LegacyWithdrawals dash={dash} />

      <p style={{ textAlign: "center", fontSize: 11, color: "var(--faint)", margin: "10px 0 0", lineHeight: 1.8, letterSpacing: ".05em" }}>
        © 2026 beti コミュニティ運営
      </p>
    </div>
  );
}

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "0 4px 11px" }}>
        <span className={s.serif} style={{ fontSize: 15, fontWeight: 700 }}>{title}</span>
        {sub && <span style={{ fontSize: 11.5, color: "var(--sub)" }}>{sub}</span>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>{children}</div>
    </div>
  );
}

function EmptyNote({ text }: { text: string }) {
  return (
    <div style={{ background: "var(--soft)", border: "1px solid var(--line)", borderRadius: 16, padding: 16, fontSize: 12.5, color: "var(--sub)", lineHeight: 1.7 }}>
      {text}
    </div>
  );
}

function StatusBadge({ label, tone }: { label: string; tone: "pending" | "ok" | "warn" | "muted" }) {
  const colors = {
    pending: { bg: "#FFF6E4", bd: "#F0DEB4", fg: "#8F6A14" },
    ok: { bg: "#E9F7F0", bd: "#C4E8D6", fg: "#187A52" },
    warn: { bg: "#FBEDE9", bd: "#F3D6CE", fg: "#B4452F" },
    muted: { bg: "var(--soft)", bd: "var(--line)", fg: "var(--sub)" },
  }[tone];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", fontSize: 11, fontWeight: 700, color: colors.fg, background: colors.bg, border: `1px solid ${colors.bd}`, borderRadius: 999, padding: "4px 10px", whiteSpace: "nowrap" }}>
      {label}
    </span>
  );
}

function buybackTone(status: string): "pending" | "ok" | "warn" | "muted" {
  if (status === "paid") return "ok";
  if (status === "rejected") return "warn";
  return "pending";
}

/* ---------- NFT 資産カード + ステーク ---------- */

function AssetCard({ asset, buyback, onUpdate }: {
  asset: PortalAsset;
  buyback?: { status: string } | undefined;
  onUpdate: (d: PortalDashboard) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = PORTAL_NFT_LABELS[asset.nft_type] || asset.nft_type;
  const total = Math.max(0, asset.purchased_units + asset.transferred_in - asset.transferred_out);

  async function doStake() {
    setBusy(true); setError(null);
    try {
      const r = await portalApi.stake(asset.nft_type);
      onUpdate(r.dashboard);
      setConfirming(false);
    } catch (e: any) {
      setError(e?.message || "ステークに失敗しました。");
    } finally { setBusy(false); }
  }

  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, padding: "16px 17px", boxShadow: "var(--shsm)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <div style={{ fontSize: 13.5, fontWeight: 700 }}>{label}</div>
        {buyback && (
          <StatusBadge label={`買い取り: ${BUYBACK_STATUS_LABELS[buyback.status] || buyback.status}`} tone={buybackTone(buyback.status)} />
        )}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 13 }}>
        <AssetStat label="保有口数" value={total} />
        <AssetStat label="ステーク済" value={asset.staked_units} accent />
        <AssetStat label="未ステーク" value={asset.unstaked_units} />
      </div>
      {asset.unstaked_units > 0 && !confirming && (
        <button type="button" className={s.btnGhost} style={{ marginTop: 13, borderColor: "var(--navy2)", color: "var(--navy2)", fontWeight: 700 }}
          onClick={() => { setConfirming(true); setError(null); }}>
          未ステーク {asset.unstaked_units} 口をステークする
        </button>
      )}
      {confirming && (
        <div style={{ marginTop: 13, background: "var(--soft)", border: "1px solid var(--line)", borderRadius: 13, padding: "13px 14px" }}>
          <div style={{ fontSize: 12.5, lineHeight: 1.7, color: "var(--sub)" }}>
            未ステークの <strong style={{ color: "var(--ink)" }}>{asset.unstaked_units} 口</strong> をすべてステークします。
            ステークした口数は今後の分配の対象になります。よろしいですか？
          </div>
          {error && <ErrorBox msg={error} />}
          <div style={{ display: "flex", gap: 9, marginTop: 12 }}>
            <button type="button" className={s.btn} style={{ padding: 12, fontSize: 13.5 }} onClick={doStake} disabled={busy}>
              {busy && <span className={s.spinner} />}{busy ? "処理中…" : "ステークする"}
            </button>
            <button type="button" className={s.btnGhost} style={{ padding: 12, fontSize: 13.5 }} onClick={() => setConfirming(false)} disabled={busy}>
              やめる
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AssetStat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div style={{ background: accent ? "rgba(43,64,112,.06)" : "var(--soft)", border: `1px solid ${accent ? "rgba(43,64,112,.18)" : "var(--line)"}`, borderRadius: 12, padding: "10px 11px" }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: accent ? "var(--navy2)" : "var(--faint)", letterSpacing: ".05em" }}>{label}</div>
      <div style={{ marginTop: 5, display: "flex", alignItems: "baseline", gap: 2 }}>
        <span className={s.serif} style={{ fontSize: 21, fontWeight: 700, lineHeight: 1, fontVariantNumeric: "tabular-nums", color: accent ? "var(--navy2)" : "var(--ink)" }}>{value}</span>
        <span style={{ fontSize: 10.5, fontWeight: 600, color: "var(--faint)" }}>口</span>
      </div>
    </div>
  );
}

/* ---------- 買い取り / 継続 パネル ---------- */

function BuybackPanel({ asset, buyback, onUpdate }: {
  asset: PortalAsset;
  buyback?: { id: number; status: string; requested_at: string } | undefined;
  onUpdate: (d: PortalDashboard) => void;
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const total = Math.max(asset.purchased_units + asset.transferred_in - asset.transferred_out, asset.staked_units);

  async function doBuyback() {
    setBusy(true); setError(null);
    try {
      const r = await portalApi.buyback();
      onUpdate(r.dashboard);
      setModalOpen(false);
    } catch (e: any) {
      setError(e?.message || "申請に失敗しました。");
    } finally { setBusy(false); }
  }

  return (
    <Section title="パチスロホイホイNFT 買い取り">
      <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, padding: "18px 17px", boxShadow: "var(--shsm)" }}>
        {buyback ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <StatusBadge label={BUYBACK_STATUS_LABELS[buyback.status] || buyback.status} tone={buybackTone(buyback.status)} />
              <span style={{ fontSize: 11.5, color: "var(--sub)", fontVariantNumeric: "tabular-nums" }}>申請日 {fmtDateShort(buyback.requested_at)}</span>
            </div>
            <div style={{ fontSize: 12.5, color: "var(--sub)", lineHeight: 1.75, marginTop: 12 }}>
              買い取りのお申し込みを受け付けています。運営にて順次確認・処理いたします。
              進捗はこのページの表示が更新されます。
            </div>
          </div>
        ) : (
          <div>
            <div style={{ fontSize: 12.5, color: "var(--sub)", lineHeight: 1.75 }}>
              パチスロホイホイNFT（保有 <strong style={{ color: "var(--ink)" }}>{total} 口</strong>）の買い取りをご希望の場合は、下のボタンからお申し込みください。
            </div>
            <button type="button" className={s.btnDanger} style={{ marginTop: 15 }} onClick={() => { setModalOpen(true); setError(null); }}>
              買い取りを申請する
            </button>
            <button type="button" className={s.btnDisabledGray} style={{ marginTop: 10 }} disabled aria-disabled="true"
              title="現在「継続」の受付は行っていません">
              継続する（現在受付停止中）
            </button>
            <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 10, lineHeight: 1.6, textAlign: "center" }}>
              買い取りを申請しない場合、お手続きは不要です。
            </div>
          </div>
        )}
      </div>

      {modalOpen && (
        <div className={s.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="bb-title" onClick={(e) => { if (e.target === e.currentTarget && !busy) setModalOpen(false); }}>
          <div className={s.modal}>
            <div style={{ width: 52, height: 52, borderRadius: "50%", background: "#FBEDE9", border: "1px solid #F3D6CE", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
              <span aria-hidden style={{ fontSize: 24 }}>⚠️</span>
            </div>
            <h2 id="bb-title" className={s.serif} style={{ margin: 0, fontSize: 18, fontWeight: 700, textAlign: "center" }}>買い取り申請の確認</h2>
            <div style={{ background: "#FBEDE9", border: "1px solid #F3D6CE", borderRadius: 13, padding: "13px 15px", margin: "16px 0 0", fontSize: 13, fontWeight: 700, color: "#B4452F", lineHeight: 1.7, textAlign: "center" }}>
              この操作は<u>二度と元に戻せません</u>。
            </div>
            <div style={{ fontSize: 12.5, color: "var(--sub)", lineHeight: 1.8, marginTop: 14 }}>
              パチスロホイホイNFT <strong style={{ color: "var(--ink)" }}>{total} 口</strong> の買い取りを申請します。
              申請後の取り消し・変更はできません。内容をご確認のうえ、確定してください。
            </div>
            {error && <ErrorBox msg={error} />}
            <button type="button" className={s.btnDanger} style={{ marginTop: 18 }} onClick={doBuyback} disabled={busy}>
              {busy && <span className={s.spinner} />}{busy ? "送信中…" : "確定して申請する"}
            </button>
            <button type="button" className={s.btnGhost} style={{ marginTop: 10 }} onClick={() => setModalOpen(false)} disabled={busy}>
              キャンセル
            </button>
          </div>
        </div>
      )}
    </Section>
  );
}

/* ---------- 出金申請 ---------- */

function WithdrawPanel({ dash, onUpdate }: { dash: PortalDashboard; onUpdate: (d: PortalDashboard) => void }) {
  const [amount, setAmount] = useState("");
  const [destination, setDestination] = useState(dash.wallet_address || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [cancelBusy, setCancelBusy] = useState<number | null>(null);

  const pendingSum = dash.withdrawals
    .filter((w) => w.status === "pending" || w.status === "processing")
    .reduce((a, w) => a + w.amount, 0);
  const available = Math.max(0, Math.round((dash.balance - pendingSum) * 100) / 100);
  const active = dash.withdrawals.filter((w) => w.status === "pending" || w.status === "processing");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null); setDone(false);
    const v = Number(amount);
    if (!Number.isFinite(v) || v <= 0) { setError("金額を正しく入力してください"); return; }
    if (v > available) { setError(`申請可能額（$${fmtUsdt(available)}）を超えています`); return; }
    if (destination.trim().length < 10) { setError("ウォレットアドレスを正しく入力してください"); return; }
    setBusy(true);
    try {
      const r = await portalApi.withdraw(Math.round(v * 100) / 100, destination.trim());
      onUpdate(r.dashboard);
      setAmount(""); setDone(true);
    } catch (e: any) {
      setError(e?.message || "申請に失敗しました。");
    } finally { setBusy(false); }
  }

  async function cancel(id: number) {
    setCancelBusy(id); setError(null);
    try {
      const r = await portalApi.cancelWithdraw(id);
      onUpdate(r.dashboard);
    } catch (e: any) {
      setError(e?.message || "取り下げに失敗しました。");
    } finally { setCancelBusy(null); }
  }

  return (
    <Section title="出金申請" sub={`申請可能額 $${fmtUsdt(available)}`}>
      {active.length > 0 && (
        <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, overflow: "hidden", boxShadow: "var(--shsm)" }}>
          {active.map((w, i) => (
            <div key={w.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "13px 15px", borderBottom: i < active.length - 1 ? "1px solid var(--hair)" : "none" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>${fmtUsdt(w.amount)}</span>
                  <StatusBadge label={WITHDRAWAL_STATUS_LABELS[w.status] || w.status} tone={w.status === "processing" ? "pending" : "muted"} />
                </div>
                <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 210 }}>{w.destination}</div>
              </div>
              {w.status === "pending" && (
                <button type="button" className={s.pgBtn} onClick={() => cancel(w.id)} disabled={cancelBusy === w.id}>
                  {cancelBusy === w.id ? "…" : "取り下げ"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, padding: "18px 17px", boxShadow: "var(--shsm)" }}>
        {available <= 0 && active.length === 0 ? (
          <div style={{ fontSize: 12.5, color: "var(--sub)", lineHeight: 1.7 }}>
            現在、出金可能な残高がありません。残高は運営からの分配によって加算されます。
          </div>
        ) : (
          <form onSubmit={submit}>
            <label htmlFor="wd-amount" style={lblStyle}>出金額 (USDT)</label>
            <input id="wd-amount" className={s.input} type="number" inputMode="decimal" min="0.01" step="0.01"
              placeholder={`最大 ${fmtUsdt(available)}`} value={amount}
              onChange={(e) => { setAmount(e.target.value); setError(null); setDone(false); }} />
            <label htmlFor="wd-dest" style={{ ...lblStyle, marginTop: 15 }}>送金先ウォレットアドレス</label>
            <input id="wd-dest" className={s.input} type="text" autoComplete="off" spellCheck={false}
              placeholder="0x… / T…" value={destination}
              onChange={(e) => { setDestination(e.target.value); setError(null); setDone(false); }} />
            <div style={{ fontSize: 11.5, color: "var(--faint)", marginTop: 9, lineHeight: 1.65 }}>
              アドレスの誤りによる送金は復元できません。よくご確認ください。
            </div>
            {error && <ErrorBox msg={error} />}
            {done && <div style={{ fontSize: 12.5, color: "var(--pos)", marginTop: 12, display: "flex", gap: 7, alignItems: "center" }}><span aria-hidden>✓</span>出金申請を受け付けました。運営にて順次処理いたします。</div>}
            <button type="submit" className={s.btn} style={{ marginTop: 16 }} disabled={busy || available <= 0}>
              {busy && <span className={s.spinner} />}{busy ? "送信中…" : "出金を申請する"}
            </button>
          </form>
        )}
      </div>
    </Section>
  );
}

/* ---------- 報酬履歴 ---------- */

function HistoryList({ dash }: { dash: PortalDashboard }) {
  const [page, setPage] = useState(0);
  const rows = dash.history;
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const slice = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "0 4px 11px" }}>
        <span className={s.serif} style={{ fontSize: 15, fontWeight: 700 }}>受取履歴</span>
        <span style={{ fontSize: 11.5, color: "var(--sub)", fontVariantNumeric: "tabular-nums" }}>全{rows.length}件</span>
      </div>
      <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, overflow: "hidden", boxShadow: "var(--shsm)" }}>
        {slice.length === 0 ? (
          <div style={{ textAlign: "center", color: "var(--sub)", fontSize: 12.5, padding: "26px 0" }}>まだ受取の記録はありません</div>
        ) : slice.map((r, i) => (
          <div key={page * PAGE_SIZE + i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "14px 16px", borderBottom: i < slice.length - 1 ? "1px solid var(--hair)" : "none" }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{fmtDateShort(r.rewarded_at)}</div>
              <div style={{ fontSize: 11, color: "var(--sub)", marginTop: 1 }}>
                {(r.nft_type && PORTAL_NFT_LABELS[r.nft_type]) || "分配"}{r.units ? ` ・ ${r.units}口分` : ""}
              </div>
            </div>
            <div style={{ textAlign: "right", flex: "none" }}>
              <div style={{ fontSize: 14, fontWeight: 800, color: "var(--pos)", fontVariantNumeric: "tabular-nums" }}>+${fmtUsdt(r.amount)}</div>
              {r.balance_after != null && (
                <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 1, fontVariantNumeric: "tabular-nums" }}>残高 ${fmtUsdt(r.balance_after)}</div>
              )}
            </div>
          </div>
        ))}
      </div>
      {pages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 13 }}>
          <button type="button" className={s.pgBtn} onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} aria-label="前のページ">
            <span aria-hidden style={{ fontSize: 14, lineHeight: 1 }}>‹</span>前へ
          </button>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--sub)", letterSpacing: ".08em", fontVariantNumeric: "tabular-nums" }}>{page + 1} / {pages}</span>
          <button type="button" className={s.pgBtn} onClick={() => setPage((p) => Math.min(pages - 1, p + 1))} disabled={page >= pages - 1} aria-label="次のページ">
            次へ<span aria-hidden style={{ fontSize: 14, lineHeight: 1 }}>›</span>
          </button>
        </div>
      )}
    </div>
  );
}

/* ---------- 過去の出金履歴 ---------- */

function LegacyWithdrawals({ dash }: { dash: PortalDashboard }) {
  const finished = dash.withdrawals.filter((w) => !["pending", "processing"].includes(w.status));
  const legacy = dash.legacy_withdrawals;
  if (finished.length === 0 && legacy.length === 0) return null;
  return (
    <Section title="出金履歴" sub={`全${finished.length + legacy.length}件`}>
      <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, overflow: "hidden", boxShadow: "var(--shsm)" }}>
        {finished.map((w, i) => (
          <div key={`n-${w.id}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "13px 15px", borderBottom: i < finished.length - 1 || legacy.length > 0 ? "1px solid var(--hair)" : "none" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{fmtDateShort(w.requested_at)}</div>
              <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 2 }}>新ポータル</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 13.5, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>${fmtUsdt(w.amount)}</span>
              <StatusBadge label={WITHDRAWAL_STATUS_LABELS[w.status] || w.status}
                tone={w.status === "paid" ? "ok" : w.status === "rejected" ? "warn" : "muted"} />
            </div>
          </div>
        ))}
        {legacy.map((w, i) => (
          <div key={`l-${w.external_id}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "13px 15px", borderBottom: i < legacy.length - 1 ? "1px solid var(--hair)" : "none" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{fmtDateShort(w.requested_at)}</div>
              <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 2 }}>旧ポータル</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 13.5, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>${fmtUsdt(w.amount_usdt)}</span>
              <StatusBadge label={LEGACY_WD_STATUS_LABELS[w.status] || `status ${w.status}`}
                tone={w.status === 2 ? "ok" : w.status === 3 ? "warn" : "muted"} />
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}
