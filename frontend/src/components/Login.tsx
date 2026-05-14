"use client";
import { useState, FormEvent, ReactNode } from "react";
import { api } from "@/lib/api";
import { saveToken } from "@/lib/auth";
import { I } from "@/lib/icons";

type Props = { onSuccess: () => void };

export default function Login({ onSuccess }: Props) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [show, setShow] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!username.trim()) { setError("ユーザー名を入力してください"); return; }
    if (!password.trim()) { setError("パスワードを入力してください"); return; }
    setLoading(true);
    try {
      const r = await api.login(username, password);
      saveToken(r.token, r.expires_at);
      onSuccess();
    } catch (err: any) {
      setError(err.message || "ユーザー名またはパスワードが正しくありません");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-shell">
      <aside className="login-brand">
        <div className="login-brand-inner">
          <div className="brand" style={{ borderBottom: "none", padding: 0, marginBottom: 0 }}>
            <div className="brand-mark" style={{ width: 32, height: 32, fontSize: 16 }}>B</div>
            <div>
              <div className="brand-name" style={{ fontSize: 17 }}>Betimail</div>
              <div className="brand-sub">NFT support inbox</div>
            </div>
          </div>

          <div className="login-hero">
            <h2 className="login-hero-title">
              受信ボックスから<br />
              <span className="login-hero-accent">そのまま運営</span>
            </h2>
            <p className="login-hero-sub">
              一斉送信・AI による下書き返信・承認フローを<br />
              ひとつの管理画面に集約します。
            </p>
          </div>

          <div className="login-features">
            <Feature
              icon={<I.Send />}
              title="一斉送信"
              sub="NFT 種別でセグメント。プレースホルダ自動置換、ジョブで進捗追跡。"
            />
            <Feature
              icon={<I.Sparkle />}
              title="AI 返信下書き"
              sub="受信メールから Claude が下書きを生成。信頼度が低いものだけ承認画面へ。"
            />
            <Feature
              icon={<I.CheckCircle />}
              title="承認フロー"
              sub="Telegram と Web の両方から承認・編集・却下が可能。"
            />
          </div>

          <div className="login-status">
            <div className="status-pill"><span className="status-dot ok" /> All systems operational</div>
            <div className="status-pill" style={{ marginLeft: "auto" }}>v2.4.1</div>
          </div>
        </div>
      </aside>

      <main className="login-main">
        <form className="login-form" onSubmit={submit}>
          <div className="login-form-head">
            <h1>サインイン</h1>
            <p>管理パネルにアクセスするにはサインインしてください。</p>
          </div>

          <div className="field">
            <label>ユーザー名</label>
            <input
              className="input"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </div>

          <div className="field">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <label>パスワード</label>
            </div>
            <div style={{ position: "relative" }}>
              <input
                className="input"
                type={show ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ paddingRight: 38 }}
              />
              <button
                type="button"
                className="icon-btn"
                onClick={() => setShow((s) => !s)}
                style={{ position: "absolute", right: 4, top: "50%", transform: "translateY(-50%)" }}
                tabIndex={-1}
                aria-label={show ? "Hide password" : "Show password"}
              >
                <I.Eye />
              </button>
            </div>
          </div>

          {error && (
            <div className="login-error">
              <I.AlertTriangle size={14} />
              <span>{error}</span>
            </div>
          )}

          <button className="btn primary lg" type="submit" disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
            {loading ? <><span className="spinner" /> サインイン中…</> : <>サインイン <I.ArrowRight /></>}
          </button>

          <div className="login-foot">
            <span>© 2026 Betimail</span>
          </div>
        </form>
      </main>
    </div>
  );
}

function Feature({ icon, title, sub }: { icon: ReactNode; title: string; sub: string }) {
  return (
    <div className="login-feature">
      <div className="login-feature-icon">{icon}</div>
      <div>
        <div className="login-feature-title">{title}</div>
        <div className="login-feature-sub">{sub}</div>
      </div>
    </div>
  );
}
