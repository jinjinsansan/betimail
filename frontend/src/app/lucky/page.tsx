"use client";
import { useEffect, useMemo, useRef, useState, FormEvent } from "react";
import {
  luckyApi, getLuckyToken, setLuckyToken, clearLuckyToken,
  fmtUsdt, fmtDateShort, type LuckyDashboard,
} from "@/lib/lucky";
import s from "./page.module.css";

type Stage = "loading" | "email" | "code" | "dashboard";

export default function LuckyPortal() {
  const [stage, setStage] = useState<Stage>("loading");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [expiresIn, setExpiresIn] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dash, setDash] = useState<LuckyDashboard | null>(null);
  const codeRef = useRef<HTMLInputElement>(null);

  // セッション復元
  useEffect(() => {
    let alive = true;
    (async () => {
      if (!getLuckyToken()) {
        if (alive) setStage("email");
        return;
      }
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
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t)) {
      setError("メールアドレスを正しく入力してください");
      return;
    }
    setBusy(true);
    try {
      const r = await luckyApi.login(t);
      if (r.verification_required) {
        setMaskedEmail(r.masked_email || t);
        setExpiresIn(r.expires_in || null);
        setStage("code");
        setTimeout(() => codeRef.current?.focus(), 60);
      } else {
        setError(
          "このメールアドレスはラッキーマスタード会員として登録されていません。NFT購入時のメールアドレスをご確認ください。"
        );
      }
    } catch (e: any) {
      setError(
        e?.status === 429
          ? "リクエストが多すぎます。少し時間をおいてください。"
          : e?.message || "送信に失敗しました。時間をおいて再度お試しください。"
      );
    } finally {
      setBusy(false);
    }
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
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError(null);
    setBusy(true);
    try {
      const r = await luckyApi.login(email.trim().toLowerCase());
      if (r.verification_required) {
        setMaskedEmail(r.masked_email || email);
        setExpiresIn(r.expires_in || null);
      }
    } catch (e: any) {
      setError(
        e?.status === 429 ? "再送は少し時間をおいてください。" : e?.message || "再送に失敗しました。"
      );
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    clearLuckyToken();
    setDash(null);
    setEmail("");
    setCode("");
    setError(null);
    setStage("email");
  }

  return (
    <div className={s.page}>
      <header className={s.topbar}>
        <div className={s.brand}>
          <div className={s.brandMark}>🌱</div>
          <div>
            <div className={s.brandName}>ラッキーマスタード</div>
            <div className={s.brandSub}>会員ページ</div>
          </div>
        </div>
        {stage === "dashboard" && (
          <button className={s.logout} onClick={logout}>ログアウト</button>
        )}
      </header>

      <div className={s.shell}>
        {stage === "loading" && (
          <div style={{ textAlign: "center", padding: "60px 0", color: "#6b7686" }}>
            <span className={s.spinner} style={{ display: "inline-block" }} /> 読み込み中…
          </div>
        )}

        {(stage === "email" || stage === "code") && (
          <div className={s.loginWrap}>
            <div className={s.hero}>
              <div className={s.heroIcon}>🌱</div>
              <h1 className={s.heroTitle}>会員ページにログイン</h1>
              <p className={s.heroSub}>
                NFT購入時にご利用いただいた<br />メールアドレスでログインできます。
              </p>
            </div>

            <div className={s.card}>
              {stage === "email" && (
                <form onSubmit={submitEmail}>
                  <label className={s.label}>メールアドレス</label>
                  <input
                    className={s.input}
                    type="email"
                    inputMode="email"
                    autoComplete="email"
                    placeholder="example@gmail.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoFocus
                  />
                  <div className={s.hint}>ご登録のメールアドレスにログインコードをお送りします。</div>
                  {error && <div className={s.error}>⚠️ <span>{error}</span></div>}
                  <button className={s.btn} disabled={busy}>
                    {busy ? <><span className={s.spinner} /> 送信中…</> : "ログインコードを送る"}
                  </button>
                </form>
              )}

              {stage === "code" && (
                <form onSubmit={submitCode}>
                  <div className={s.notice}>
                    {maskedEmail} 宛にログインコードを送信しました。
                    {expiresIn ? `（有効期限 約${Math.max(1, Math.floor(expiresIn / 60))}分）` : ""}
                  </div>
                  <label className={s.label}>ログインコード（6桁）</label>
                  <input
                    ref={codeRef}
                    className={`${s.input} ${s.codeInput}`}
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    placeholder="••••••"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  />
                  {error && <div className={s.error}>⚠️ <span>{error}</span></div>}
                  <button className={s.btn} disabled={busy}>
                    {busy ? <><span className={s.spinner} /> 確認中…</> : "ログイン"}
                  </button>
                  <button type="button" className={`${s.btn} ${s.btnGhost}`} onClick={resend} disabled={busy}>
                    コードを再送する
                  </button>
                </form>
              )}
            </div>

            <p className={s.foot}>© 2026 beti コミュニティ運営</p>
          </div>
        )}

        {stage === "dashboard" && dash && <Dashboard dash={dash} />}
      </div>
    </div>
  );
}

function Dashboard({ dash }: { dash: LuckyDashboard }) {
  const hasNft = (dash.nft_count || 0) > 0;
  return (
    <>
      <div className={s.greeting}>
        <div className={s.greetingName}>{dash.name ? `${dash.name} 様` : "ようこそ"}</div>
        <div className={s.greetingSub}>ラッキーマスタード 報酬ダッシュボード</div>
      </div>

      <div className={s.tiles}>
        <div className={s.tile}>
          <div className={s.tileLabel}>🎫 保有NFT</div>
          <div className={s.tileValue}>{dash.nft_count}<span className={s.tileUnit}>枚</span></div>
          <div className={s.tileFoot}>報酬対象のNFT枚数</div>
        </div>
        <div className={`${s.tile} ${s.tileAccent}`}>
          <div className={s.tileLabel}>✨ 本日の報酬</div>
          <div className={s.tileValue}><span className={s.usd}>${fmtUsdt(dash.today_reward)}</span></div>
          <div className={s.tileFoot}>{dash.nft_count}枚 × ${dash.rate.toFixed(4)}/枚</div>
        </div>
        <div className={s.tile}>
          <div className={s.tileLabel}>📈 累計報酬</div>
          <div className={s.tileValue}><span className={s.usd}>${fmtUsdt(dash.cumulative_reward)}</span></div>
          <div className={s.tileFoot}>これまでの合計</div>
        </div>
        <div className={s.tile}>
          <div className={s.tileLabel}>💰 残高</div>
          <div className={s.tileValue}><span className={s.usd}>${fmtUsdt(dash.balance)}</span></div>
          <div className={s.tileFoot}>現在のウォレット残高</div>
        </div>
      </div>

      {!hasNft && (
        <div className={s.zeroNote}>
          現在、報酬対象のラッキーマスタードNFTが確認できません。
          お心当たりがない場合は support@betimail.uk までお問い合わせください。
        </div>
      )}

      <div className={s.section}>
        <div className={s.sectionHead}>
          <span className={s.sectionTitle}>報酬の推移</span>
          <span className={s.sectionMeta}>残高の積み上がり</span>
        </div>
        <div className={s.chartCard}>
          <BalanceChart series={dash.series} />
        </div>
      </div>

      <div className={s.section}>
        <div className={s.sectionHead}>
          <span className={s.sectionTitle}>報酬履歴</span>
          <span className={s.sectionMeta}>最新{Math.min(dash.history.length, 120)}件</span>
        </div>
        {dash.history.length === 0 ? (
          <div className={s.chartCard}><div className={s.chartEmpty}>まだ報酬の記録はありません</div></div>
        ) : (
          <div className={s.histList}>
            {dash.history.map((r, i) => (
              <div className={s.histRow} key={i}>
                <div>
                  <div className={s.histDate}>{fmtDateShort(r.rewarded_at)}</div>
                  <div className={s.histSub}>{r.nft_count ?? "—"}枚分</div>
                </div>
                <div className={s.histRight}>
                  <div className={s.histAmt}>+${fmtUsdt(r.amount)}</div>
                  <div className={s.histBal}>残高 ${fmtUsdt(r.balance_after)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className={s.foot}>
        最終報酬: {fmtDateShort(dash.last_reward_at)}<br />
        © 2026 beti コミュニティ運営
      </p>
    </>
  );
}

// 残高推移の SVG エリアチャート（軽量・依存なし）
function BalanceChart({ series }: { series: LuckyDashboard["series"] }) {
  const pts = useMemo(
    () => series.filter((d) => d.balance_after != null).map((d) => ({ date: d.date, v: Number(d.balance_after) })),
    [series]
  );
  if (pts.length < 2) {
    return <div className={s.chartEmpty}>グラフを表示するには報酬データが不足しています</div>;
  }
  const W = 320, H = 110, PAD = 6;
  const xs = pts.map((_, i) => PAD + (i * (W - PAD * 2)) / (pts.length - 1));
  const vals = pts.map((p) => p.v);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const ys = vals.map((v) => H - PAD - ((v - min) / span) * (H - PAD * 2));
  const line = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const area = `${line} L${xs[xs.length - 1].toFixed(1)},${H} L${xs[0].toFixed(1)},${H} Z`;
  return (
    <>
      <svg className={s.chartSvg} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="残高の推移">
        <defs>
          <linearGradient id="lkfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e0a82e" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#e0a82e" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#lkfill)" />
        <path d={line} fill="none" stroke="#b9831a" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div className={s.chartAxis}>
        <span>{fmtDateShort(pts[0].date)}</span>
        <span>{fmtDateShort(pts[pts.length - 1].date)}</span>
      </div>
    </>
  );
}
