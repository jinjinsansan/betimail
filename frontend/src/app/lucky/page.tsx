"use client";
import { useEffect, useMemo, useRef, useState, FormEvent, PointerEvent } from "react";
import {
  luckyApi, getLuckyToken, setLuckyToken, clearLuckyToken,
  fmtUsdt, fmtDateShort, type LuckyDashboard,
} from "@/lib/lucky";
import s from "./page.module.css";

type Stage = "loading" | "email" | "code" | "dashboard";
const PAGE_SIZE = 6;

export default function LuckyPortal() {
  const [stage, setStage] = useState<Stage>("loading");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [expiresIn, setExpiresIn] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resent, setResent] = useState(false);
  const [dash, setDash] = useState<LuckyDashboard | null>(null);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!getLuckyToken()) { if (alive) setStage("email"); return; }
      try {
        const d = await luckyApi.me();
        if (alive) { setDash(d); setStage("dashboard"); }
      } catch {
        clearLuckyToken();
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
      const r = await luckyApi.login(t);
      if (r.verification_required) {
        setMaskedEmail(r.masked_email || t);
        setExpiresIn(r.expires_in || null);
        setStage("code");
        setTimeout(() => codeRef.current?.focus(), 60);
      } else {
        setError("このメールアドレスはラッキーマスタード会員として登録されていません。NFT購入時のメールアドレスをご確認ください。");
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
      const r = await luckyApi.verify(email.trim().toLowerCase(), c);
      setLuckyToken(r.token);
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
      const r = await luckyApi.login(email.trim().toLowerCase());
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
    clearLuckyToken();
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
              <div className={s.serif} style={{ fontSize: 16, fontWeight: 700, letterSpacing: ".04em" }}>ラッキーマスタード</div>
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
              <span className={s.spinner} /> &nbsp;読み込み中…
            </div>
          )}

          {isLogin && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", padding: "24px 22px 40px", maxWidth: 430, width: "100%", margin: "0 auto" }}>
              <div style={{ textAlign: "center", marginBottom: 30 }}>
                <Mark size={66} ringed />
                <div style={{ fontSize: 10.5, color: "var(--gold-deep)", fontWeight: 700, letterSpacing: ".24em", margin: "20px 0 10px" }}>LUCKY MUSTARD</div>
                <h1 className={s.serif} style={{ margin: "0 0 10px", fontSize: 25, fontWeight: 700, letterSpacing: ".02em" }}>会員ページにログイン</h1>
                <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.8, color: "var(--sub)" }}>
                  NFT購入時にご利用いただいた<br />メールアドレスでログインできます。
                </p>
              </div>

              <div style={{ position: "relative", background: "var(--card)", border: "1px solid var(--line)", borderRadius: 24, padding: "26px 22px", boxShadow: "var(--sh)" }}>
                <div aria-hidden style={{ position: "absolute", top: 0, left: 32, right: 32, height: 2, background: "linear-gradient(90deg,transparent,var(--gold),transparent)", opacity: .7 }} />

                {stage === "email" && (
                  <form onSubmit={submitEmail}>
                    <label htmlFor="lk-email" style={lblStyle}>メールアドレス</label>
                    <input id="lk-email" className={s.input} type="email" inputMode="email" autoComplete="email"
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
                    <label htmlFor="lk-code" style={lblStyle}>ログインコード（6桁）</label>
                    <input id="lk-code" ref={codeRef} className={`${s.input} ${s.codeInput}`} type="text"
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

          {stage === "dashboard" && dash && <Dashboard dash={dash} />}
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
  // マスタードの種をかたどったゴールドのマーク
  return (
    <svg viewBox="0 0 64 64" style={{ width: size, height: size, display: "block", margin: ringed ? "0 auto" : undefined, flex: "none" }} aria-hidden>
      {ringed && <circle cx="32" cy="32" r="30" fill="var(--card)" stroke="var(--gold)" strokeWidth="1.1" />}
      {!ringed && <circle cx="32" cy="32" r="29" fill="none" stroke="var(--gold)" strokeWidth="1.3" />}
      <circle cx="32" cy="32" r="24.5" fill="none" stroke="var(--gold)" strokeWidth="0.7" strokeOpacity="0.5" />
      <path d="M32 18 C39 22 40.5 31.5 35.5 40 C34 42.4 33 43.6 32 44.8 C31 43.6 30 42.4 28.5 40 C23.5 31.5 25 22 32 18 Z" fill="var(--gold)" />
    </svg>
  );
}

/* ---------- count-up ---------- */
function useCountUp(target: number, run: boolean, ms = 850): number {
  const [v, setV] = useState(run ? 0 : target);
  useEffect(() => {
    if (!run) { setV(target); return; }
    let raf = 0;
    let start = 0;
    const tick = (now: number) => {
      if (!start) start = now;
      const t = Math.min(1, (now - start) / ms);
      const e = 1 - Math.pow(1 - t, 3);
      setV(target * e);
      if (t < 1) raf = requestAnimationFrame(tick);
      else setV(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, run, ms]);
  return v;
}

function Dashboard({ dash }: { dash: LuckyDashboard }) {
  const [animate, setAnimate] = useState(true);
  useEffect(() => { setAnimate(true); }, []);
  const balance = useCountUp(dash.balance, animate);
  const today = useCountUp(dash.today_reward, animate);
  const cum = useCountUp(dash.cumulative_reward, animate);
  const nftAnim = useCountUp(dash.nft_count, animate, 600);

  const lastDate = (dash.last_reward_at || "").slice(0, 10).replace(/-/g, "/");

  return (
    <div style={{ padding: "20px 18px 44px", display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ marginTop: 4 }}>
        <div style={{ fontSize: 10.5, color: "var(--gold-deep)", fontWeight: 700, letterSpacing: ".22em" }}>MEMBER DASHBOARD</div>
        <div className={s.serif} style={{ fontSize: 23, fontWeight: 700, letterSpacing: ".02em", marginTop: 5 }}>
          {dash.name ? `${dash.name} 様` : "ようこそ"}
        </div>
      </div>

      {/* HERO balance */}
      <div style={{ position: "relative", borderRadius: 26, padding: "28px 26px 24px", overflow: "hidden", background: "linear-gradient(158deg,var(--espresso2),var(--espresso))", border: "1px solid rgba(201,154,51,.26)", boxShadow: "0 24px 50px -24px rgba(20,16,8,.7), inset 0 1px 0 rgba(255,255,255,.04)" }}>
        <div aria-hidden style={{ position: "absolute", inset: 0, background: "radial-gradient(90% 70% at 88% -10%, var(--gold-glow), transparent 60%)" }} />
        <div aria-hidden style={{ position: "absolute", top: 0, left: 26, right: 26, height: 1.5, background: "linear-gradient(90deg,transparent,var(--gold2),transparent)", opacity: .8 }} />
        <div style={{ position: "relative" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <div>
              <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".16em", color: "var(--gold2)" }}>CURRENT BALANCE</div>
              <div style={{ fontSize: 12, color: "var(--creamsub)", marginTop: 6 }}>現在の残高 (USDT)</div>
            </div>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 700, color: "var(--gold2)", background: "rgba(201,154,51,.14)", border: "1px solid rgba(201,154,51,.32)", borderRadius: 999, padding: "6px 12px", fontVariantNumeric: "tabular-nums" }}>
              ▲ 本日 +${fmtUsdt(dash.today_reward)}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginTop: 14, color: "var(--cream)" }}>
            <span className={s.serif} style={{ fontSize: 26, fontWeight: 600, color: "var(--gold2)" }}>$</span>
            <span className={s.serif} style={{ fontSize: 50, fontWeight: 700, lineHeight: 1, letterSpacing: "-.01em", fontVariantNumeric: "tabular-nums" }}>{fmtUsdt(balance)}</span>
          </div>
          <div aria-hidden style={{ height: 1, background: "linear-gradient(90deg,rgba(201,154,51,.4),transparent)", margin: "18px 0 0" }} />
          <div style={{ fontSize: 11.5, color: "var(--creamsub)", marginTop: 13, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--gold2)", display: "inline-block" }} />
            毎日 20:00 に報酬が自動で積み上がります
          </div>
        </div>
      </div>

      {/* tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 13 }}>
        <div style={{ gridColumn: "1 / -1", position: "relative", background: "var(--soft)", border: "1px solid var(--line)", borderRadius: 19, padding: "17px 18px", boxShadow: "var(--shsm)", overflow: "hidden" }}>
          <div aria-hidden style={{ position: "absolute", top: 0, left: 0, width: 3, height: "100%", background: "linear-gradient(180deg,var(--gold2),var(--gold))" }} />
          <div style={tileLabel}>本日の報酬</div>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 10, marginTop: 8 }}>
            <div className={s.serif} style={{ fontSize: 30, fontWeight: 700, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>${fmtUsdt(today)}</div>
            <div style={{ fontSize: 11.5, color: "var(--sub)", textAlign: "right", lineHeight: 1.5, fontVariantNumeric: "tabular-nums" }}>{dash.nft_count}枚 × ${dash.rate.toFixed(4)}/枚</div>
          </div>
        </div>
        <div style={tileCard}>
          <div style={tileLabel}>保有NFT</div>
          <div style={{ marginTop: 9, display: "flex", alignItems: "baseline", gap: 3 }}>
            <span className={s.serif} style={{ fontSize: 30, fontWeight: 700, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{Math.round(nftAnim)}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--sub)" }}>枚</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 7 }}>報酬対象のNFT</div>
        </div>
        <div style={tileCard}>
          <div style={tileLabel}>累計報酬</div>
          <div style={{ marginTop: 9, display: "flex", alignItems: "baseline", gap: 2 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: "var(--sub)" }}>$</span>
            <span className={s.serif} style={{ fontSize: 26, fontWeight: 700, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{fmtUsdt(cum)}</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 7 }}>これまでの合計</div>
        </div>
      </div>

      {dash.nft_count === 0 && (
        <div style={{ background: "var(--soft)", border: "1px solid var(--line)", borderRadius: 16, padding: 16, fontSize: 12.5, color: "var(--sub)", lineHeight: 1.7 }}>
          現在、報酬対象のラッキーマスタードNFTが確認できません。お心当たりがない場合は support@betimail.uk までお問い合わせください。
        </div>
      )}

      <BalanceChart series={dash.series} />

      <HistoryList dash={dash} />

      <p style={{ textAlign: "center", fontSize: 11, color: "var(--faint)", margin: "10px 0 0", lineHeight: 1.8, letterSpacing: ".05em" }}>
        最終報酬: {lastDate || "—"}<br />© 2026 beti コミュニティ運営
      </p>
    </div>
  );
}

const tileCard: React.CSSProperties = { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, padding: "16px 17px", boxShadow: "var(--shsm)" };
const tileLabel: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: "var(--gold-deep)", letterSpacing: ".08em" };

/* ---------- chart ---------- */
function BalanceChart({ series }: { series: LuckyDashboard["series"] }) {
  const [active, setActive] = useState<number | null>(null);
  const chart = useMemo(() => {
    const pts = series.filter((d) => d.balance_after != null).map((d) => ({ date: d.date, v: Number(d.balance_after) }));
    if (pts.length < 2) return null;
    const X0 = 14, X1 = 586, Y0 = 18, Y1 = 176;
    const xs = pts.map((_, i) => X0 + (i * (X1 - X0)) / (pts.length - 1));
    const vs = pts.map((p) => p.v);
    const min = Math.min(...vs), max = Math.max(...vs), span = max - min || 1;
    const ys = vs.map((v) => Y1 - ((v - min) / span) * (Y1 - Y0));
    const line = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
    const area = `${line} L${xs[xs.length - 1].toFixed(1)},200 L${xs[0].toFixed(1)},200 Z`;
    return { pts, xs, ys, line, area };
  }, [series]);

  function onMove(e: PointerEvent<HTMLDivElement>) {
    if (!chart) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    setActive(Math.round(ratio * (chart.pts.length - 1)));
  }

  const tipIdx = chart ? (active ?? chart.pts.length - 1) : 0;
  const tipPt = chart?.pts[tipIdx];

  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 21, padding: "20px 17px 15px", boxShadow: "var(--shsm)" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", padding: "0 3px", marginBottom: 8 }}>
        <div>
          <div className={s.serif} style={{ fontSize: 15, fontWeight: 700 }}>報酬の推移</div>
          <div style={{ fontSize: 11.5, color: "var(--sub)", marginTop: 2 }}>残高の積み上がり（直近{chart?.pts.length ?? 0}日）</div>
        </div>
        {tipPt && (
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 10, color: "var(--faint)", fontWeight: 700, letterSpacing: ".06em" }}>{fmtDateShort(tipPt.date)} 残高</div>
            <div className={s.serif} style={{ fontSize: 17, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "var(--gold-deep)", marginTop: 1 }}>${fmtUsdt(tipPt.v)}</div>
          </div>
        )}
      </div>

      {!chart ? (
        <div style={{ textAlign: "center", color: "var(--sub)", fontSize: 12.5, padding: "40px 0" }}>
          グラフを表示するには報酬データが不足しています
        </div>
      ) : (
        <>
          <div className={s.chartBox} onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setActive(null)}>
            <svg viewBox="0 0 600 200" preserveAspectRatio="none" role="img" aria-label="残高の推移グラフ" style={{ display: "block", width: "100%", height: "100%", overflow: "visible" }}>
              <defs>
                <linearGradient id="lkfill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--gold)" stopOpacity="0.24" />
                  <stop offset="100%" stopColor="var(--gold)" stopOpacity="0" />
                </linearGradient>
              </defs>
              {[18, 70, 123, 176].map((y) => (
                <line key={y} x1="14" y1={y} x2="586" y2={y} stroke={y === 176 ? "var(--line)" : "var(--hair)"} strokeWidth="1" vectorEffect="non-scaling-stroke" />
              ))}
              <path d={chart.area} fill="url(#lkfill)" />
              <path d={chart.line} fill="none" stroke="var(--gold-deep)" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke"
                pathLength={1} style={{ strokeDasharray: 1, strokeDashoffset: 1, animation: "lk-draw 1.2s .15s cubic-bezier(.4,0,.2,1) forwards" }} />
            </svg>
            {active != null && (
              <>
                <div aria-hidden style={{ position: "absolute", top: 8, bottom: 24, width: 1.5, background: "var(--gold)", opacity: .5, left: `${(chart.xs[active] / 600) * 100}%`, transform: "translateX(-50%)" }} />
                <div aria-hidden style={{ position: "absolute", width: 12, height: 12, borderRadius: "50%", background: "var(--card)", border: "2.5px solid var(--gold-deep)", boxShadow: "0 1px 5px rgba(0,0,0,.2)", left: `${(chart.xs[active] / 600) * 100}%`, top: `${(chart.ys[active] / 200) * 176}px`, transform: "translate(-50%,-50%)" }} />
              </>
            )}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", padding: "0 4px", fontSize: 11, color: "var(--faint)", fontVariantNumeric: "tabular-nums" }}>
            <span>{fmtDateShort(chart.pts[0].date)}</span>
            <span>{fmtDateShort(chart.pts[chart.pts.length - 1].date)}</span>
          </div>
        </>
      )}
    </div>
  );
}

/* ---------- history with pagination ---------- */
function HistoryList({ dash }: { dash: LuckyDashboard }) {
  const [page, setPage] = useState(0);
  const rows = dash.history;
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const slice = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "0 4px 11px" }}>
        <span className={s.serif} style={{ fontSize: 15, fontWeight: 700 }}>報酬履歴</span>
        <span style={{ fontSize: 11.5, color: "var(--sub)", fontVariantNumeric: "tabular-nums" }}>全{rows.length}件</span>
      </div>
      <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 19, overflow: "hidden", boxShadow: "var(--shsm)" }}>
        {slice.length === 0 ? (
          <div style={{ textAlign: "center", color: "var(--sub)", fontSize: 12.5, padding: "26px 0" }}>まだ報酬の記録はありません</div>
        ) : slice.map((r, i) => (
          <div key={page * PAGE_SIZE + i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "14px 16px", borderBottom: i < slice.length - 1 ? "1px solid var(--hair)" : "none" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
              <div style={{ width: 36, height: 36, borderRadius: "50%", background: "var(--soft)", border: "1px solid var(--line)", display: "flex", alignItems: "center", justifyContent: "center", flex: "none" }}>
                <span style={{ width: 10, height: 10, borderRadius: "50% 50% 50% 2px", background: "var(--gold)", transform: "rotate(-12deg)" }} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{fmtDateShort(r.rewarded_at)}</div>
                <div style={{ fontSize: 11, color: "var(--sub)", marginTop: 1 }}>{r.nft_count ?? "—"}枚分</div>
              </div>
            </div>
            <div style={{ textAlign: "right", flex: "none" }}>
              <div style={{ fontSize: 14, fontWeight: 800, color: "var(--pos)", fontVariantNumeric: "tabular-nums" }}>+${fmtUsdt(r.amount)}</div>
              <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 1, fontVariantNumeric: "tabular-nums" }}>残高 ${fmtUsdt(r.balance_after)}</div>
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
