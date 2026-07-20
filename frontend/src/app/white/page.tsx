"use client";
import { useEffect, useRef, useState, FormEvent } from "react";
import {
  whiteApi, getWhiteToken, setWhiteToken, clearWhiteToken,
  fmtUsdt, fmtDateShort, WHITE_WD_STATUS_LABELS, WHITE_LEGACY_WD_STATUS_LABELS,
  type WhiteDashboard,
} from "@/lib/white";
import s from "./page.module.css";

type Stage = "loading" | "email" | "code" | "dashboard";

export default function WhiteDashboardPage() {
  const [stage, setStage] = useState<Stage>("loading");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [expiresIn, setExpiresIn] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resent, setResent] = useState(false);
  const [dash, setDash] = useState<WhiteDashboard | null>(null);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!getWhiteToken()) { if (alive) setStage("email"); return; }
      try {
        const d = await whiteApi.me();
        if (alive) { setDash(d); setStage("dashboard"); }
      } catch {
        clearWhiteToken();
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
      const r = await whiteApi.login(t);
      if (r.verification_required) {
        setMaskedEmail(r.masked_email || t);
        setExpiresIn(r.expires_in || null);
        setStage("code");
        setTimeout(() => codeRef.current?.focus(), 60);
      } else {
        setError("このメールアドレスは会員として登録されていません。旧ダッシュボード登録時のメールアドレスをご確認ください。");
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
      const r = await whiteApi.verify(email.trim().toLowerCase(), c);
      setWhiteToken(r.token);
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
      const r = await whiteApi.login(email.trim().toLowerCase());
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
    clearWhiteToken();
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
              <div className={s.serif} style={{ fontSize: 16, fontWeight: 700, letterSpacing: ".04em" }}>白のダッシュボード</div>
              <div style={{ fontSize: 10, color: "var(--silver)", fontWeight: 700, letterSpacing: ".22em" }}>WHITE DASHBOARD</div>
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
                <div style={{ fontSize: 10.5, color: "var(--silver)", fontWeight: 700, letterSpacing: ".24em", margin: "20px 0 10px" }}>WHITE DASHBOARD</div>
                <h1 className={s.serif} style={{ margin: "0 0 10px", fontSize: 25, fontWeight: 700, letterSpacing: ".02em" }}>会員ページにログイン</h1>
                <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.8, color: "var(--sub)" }}>
                  旧ダッシュボードにご登録いただいた<br />メールアドレスでログインできます。
                </p>
              </div>

              <div style={{ position: "relative", background: "var(--card)", border: "1px solid var(--line)", borderRadius: 24, padding: "26px 22px", boxShadow: "var(--sh)" }}>
                <div aria-hidden style={{ position: "absolute", top: 0, left: 32, right: 32, height: 2, background: "linear-gradient(90deg,transparent,var(--silver),transparent)", opacity: .8 }} />

                {stage === "email" && (
                  <form onSubmit={submitEmail}>
                    <label htmlFor="wt-email" style={lblStyle}>メールアドレス</label>
                    <input id="wt-email" className={s.input} type="email" inputMode="email" autoComplete="email"
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
                    <label htmlFor="wt-code" style={lblStyle}>ログインコード（6桁）</label>
                    <input id="wt-code" ref={codeRef} className={`${s.input} ${s.codeInput}`} type="text"
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
  display: "block", fontSize: 12, fontWeight: 700, color: "var(--graphite2)",
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
  // 白いダイヤモンド（シルバー枠）のマーク
  return (
    <svg viewBox="0 0 64 64" style={{ width: size, height: size, display: "block", margin: ringed ? "0 auto" : undefined, flex: "none" }} aria-hidden>
      {ringed && <circle cx="32" cy="32" r="30" fill="var(--card)" stroke="var(--silver)" strokeWidth="1.1" />}
      {!ringed && <circle cx="32" cy="32" r="29" fill="none" stroke="var(--silver)" strokeWidth="1.3" />}
      <path d="M32 16 L46 30 L32 48 L18 30 Z" fill="#fff" stroke="var(--graphite2)" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M18 30 H46 M32 16 L26 30 L32 48 M32 16 L38 30 L32 48" fill="none" stroke="var(--silver)" strokeWidth="1" strokeLinejoin="round" />
    </svg>
  );
}

/* ================= ダッシュボード ================= */

function Dashboard({ dash, onUpdate }: { dash: WhiteDashboard; onUpdate: (d: WhiteDashboard) => void }) {
  return (
    <div style={{ padding: "20px 18px 44px", display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ marginTop: 4 }}>
        <div style={{ fontSize: 10.5, color: "var(--silver)", fontWeight: 700, letterSpacing: ".22em" }}>MEMBER DASHBOARD</div>
        <div className={s.serif} style={{ fontSize: 23, fontWeight: 700, letterSpacing: ".02em", marginTop: 5 }}>
          {dash.name ? `${dash.name} 様` : "ようこそ"}
        </div>
      </div>

      {/* HERO balance（白×シルバー枠） */}
      <div style={{ position: "relative", borderRadius: 26, padding: "28px 26px 24px", overflow: "hidden", background: "linear-gradient(158deg,#ffffff,#f2f4f7)", border: "1.5px solid var(--silver2)", boxShadow: "var(--sh)" }}>
        <div aria-hidden style={{ position: "absolute", top: 0, left: 26, right: 26, height: 1.5, background: "linear-gradient(90deg,transparent,var(--silver),transparent)" }} />
        <div style={{ position: "relative" }}>
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".16em", color: "var(--graphite2)" }}>CURRENT BALANCE</div>
          <div style={{ fontSize: 12, color: "var(--sub)", marginTop: 6 }}>ウォレット残高 (USDT)</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginTop: 14 }}>
            <span className={s.serif} style={{ fontSize: 26, fontWeight: 600, color: "var(--graphite2)" }}>$</span>
            <span className={s.serif} style={{ fontSize: 50, fontWeight: 700, lineHeight: 1, letterSpacing: "-.01em", fontVariantNumeric: "tabular-nums" }}>{fmtUsdt(dash.balance)}</span>
          </div>
          <div aria-hidden style={{ height: 1, background: "linear-gradient(90deg,var(--silver2),transparent)", margin: "18px 0 0" }} />
          <div style={{ fontSize: 11.5, color: "var(--sub)", marginTop: 13, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--silver)", display: "inline-block" }} />
            旧ダッシュボードの残高を引き継いでいます
          </div>
        </div>
      </div>

      {/* NFT 保有枚数 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 13 }}>
        <UnitTile label="会員権NFT" units={dash.kaiin_units} />
        <UnitTile label="パチスロホイホイ" units={dash.hoihoi_units} />
      </div>

      {/* 出金申請 */}
      <WithdrawPanel dash={dash} onUpdate={onUpdate} />

      {/* 出金履歴 */}
      <WithdrawHistory dash={dash} />

      <p style={{ textAlign: "center", fontSize: 11, color: "var(--faint)", margin: "10px 0 0", lineHeight: 1.8, letterSpacing: ".05em" }}>
        © 2026 beti コミュニティ運営
      </p>
    </div>
  );
}

function UnitTile({ label, units }: { label: string; units: number }) {
  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, padding: "16px 17px", boxShadow: "var(--shsm)" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--graphite2)", letterSpacing: ".08em" }}>{label}</div>
      <div style={{ marginTop: 9, display: "flex", alignItems: "baseline", gap: 3 }}>
        <span className={s.serif} style={{ fontSize: 30, fontWeight: 700, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{units}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--sub)" }}>口</span>
      </div>
      <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 7 }}>保有口数</div>
    </div>
  );
}

const PRIORITY_NOTE = "出金申請は受け付けておりますが、送金はポータルサイト側の出金処理を優先して行うため、今しばらくお待ちください。";

function WithdrawPanel({ dash, onUpdate }: { dash: WhiteDashboard; onUpdate: (d: WhiteDashboard) => void }) {
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
      const r = await whiteApi.withdraw(Math.round(v * 100) / 100, destination.trim());
      onUpdate(r.dashboard);
      setAmount(""); setDone(true);
    } catch (e: any) {
      setError(e?.message || "申請に失敗しました。");
    } finally { setBusy(false); }
  }

  async function cancel(id: number) {
    setCancelBusy(id); setError(null);
    try {
      const r = await whiteApi.cancelWithdraw(id);
      onUpdate(r.dashboard);
    } catch (e: any) {
      setError(e?.message || "取り下げに失敗しました。");
    } finally { setCancelBusy(null); }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "0 4px 11px" }}>
        <span className={s.serif} style={{ fontSize: 15, fontWeight: 700 }}>出金申請</span>
        <span style={{ fontSize: 11.5, color: "var(--sub)", fontVariantNumeric: "tabular-nums" }}>申請可能額 ${fmtUsdt(available)}</span>
      </div>

      {/* 優先順の注意書き（常設） */}
      <div style={{ display: "flex", gap: 9, alignItems: "flex-start", background: "#FFF9E8", border: "1px solid #F0E2B8", borderRadius: 14, padding: "12px 14px", marginBottom: 12, fontSize: 12, color: "#7A611B", lineHeight: 1.7 }}>
        <span aria-hidden style={{ flex: "none" }}>ℹ️</span>
        <span>{PRIORITY_NOTE}</span>
      </div>

      {active.length > 0 && (
        <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, overflow: "hidden", boxShadow: "var(--shsm)", marginBottom: 12 }}>
          {active.map((w, i) => (
            <div key={w.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "13px 15px", borderBottom: i < active.length - 1 ? "1px solid var(--hair)" : "none" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>${fmtUsdt(w.amount)}</span>
                  <StatusBadge label={WHITE_WD_STATUS_LABELS[w.status] || w.status} tone={w.status === "processing" ? "pending" : "muted"} />
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
            現在、出金可能な残高がありません。
          </div>
        ) : (
          <form onSubmit={submit}>
            <label htmlFor="wwd-amount" style={lblStyle}>出金額 (USDT)</label>
            <input id="wwd-amount" className={s.input} type="number" inputMode="decimal" min="0.01" step="0.01"
              placeholder={`最大 ${fmtUsdt(available)}`} value={amount}
              onChange={(e) => { setAmount(e.target.value); setError(null); setDone(false); }} />
            <label htmlFor="wwd-dest" style={{ ...lblStyle, marginTop: 15 }}>送金先ウォレットアドレス</label>
            <input id="wwd-dest" className={s.input} type="text" autoComplete="off" spellCheck={false}
              placeholder="0x… / T…" value={destination}
              onChange={(e) => { setDestination(e.target.value); setError(null); setDone(false); }} />
            <div style={{ fontSize: 11.5, color: "var(--faint)", marginTop: 9, lineHeight: 1.65 }}>
              アドレスの誤りによる送金は復元できません。よくご確認ください。
            </div>
            {error && <ErrorBox msg={error} />}
            {done && (
              <div style={{ fontSize: 12.5, color: "var(--pos)", marginTop: 12, lineHeight: 1.7 }}>
                <span aria-hidden>✓</span> 出金申請を受け付けました。{PRIORITY_NOTE}
              </div>
            )}
            <button type="submit" className={s.btn} style={{ marginTop: 16 }} disabled={busy || available <= 0}>
              {busy && <span className={s.spinner} />}{busy ? "送信中…" : "出金を申請する"}
            </button>
          </form>
        )}
      </div>
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

function WithdrawHistory({ dash }: { dash: WhiteDashboard }) {
  const finished = dash.withdrawals.filter((w) => !["pending", "processing"].includes(w.status));
  const legacy = dash.legacy_withdrawals;
  if (finished.length === 0 && legacy.length === 0) return null;
  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "0 4px 11px" }}>
        <span className={s.serif} style={{ fontSize: 15, fontWeight: 700 }}>出金履歴</span>
        <span style={{ fontSize: 11.5, color: "var(--sub)", fontVariantNumeric: "tabular-nums" }}>全{finished.length + legacy.length}件</span>
      </div>
      <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, overflow: "hidden", boxShadow: "var(--shsm)" }}>
        {finished.map((w, i) => (
          <div key={`n-${w.id}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "13px 15px", borderBottom: i < finished.length - 1 || legacy.length > 0 ? "1px solid var(--hair)" : "none" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{fmtDateShort(w.requested_at)}</div>
              <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 2 }}>新ダッシュボード</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 13.5, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>${fmtUsdt(w.amount)}</span>
              <StatusBadge label={WHITE_WD_STATUS_LABELS[w.status] || w.status}
                tone={w.status === "paid" ? "ok" : w.status === "rejected" ? "warn" : "muted"} />
            </div>
          </div>
        ))}
        {legacy.map((w, i) => (
          <div key={`l-${w.external_id}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "13px 15px", borderBottom: i < legacy.length - 1 ? "1px solid var(--hair)" : "none" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{fmtDateShort(w.requested_at)}</div>
              <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 2 }}>旧ダッシュボード</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 13.5, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>${fmtUsdt(w.amount_usdt)}</span>
              <StatusBadge label={WHITE_LEGACY_WD_STATUS_LABELS[w.status] || `status ${w.status}`}
                tone={w.status === 2 ? "ok" : "muted"} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
