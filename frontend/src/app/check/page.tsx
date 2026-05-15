"use client";
import { useState, useRef, FormEvent, KeyboardEvent } from "react";
import { api } from "@/lib/api";
import { I } from "@/lib/icons";
import { nftBadgeClass, nftLabel } from "@/lib/ui";

type Result =
  | { found: true; name?: string; nft_types?: string[] }
  | { found: false }
  | null;

type Toast = { id: string; msg: string; isError?: boolean };

const SUPPORT_EMAIL = "support@betimail.uk";

export default function CheckPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  function showToast(msg: string, isError = false) {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, msg, isError }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 2400);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setError("メールアドレスを正しく入力してください");
      return;
    }
    setLoading(true);
    try {
      const r = await api.publicCheck(trimmed);
      setResult(r);
    } catch (e: any) {
      const msg =
        e?.status === 429
          ? "確認のリクエストが多すぎます。少し時間をおいてからお試しください。"
          : e?.message || "確認に失敗しました。少し時間をおいてお試しください。";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setEmail("");
    setResult(null);
    setError(null);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  return (
    <div className="check-page">
      <header className="check-topbar">
        <div className="check-brand">
          <div className="brand-mark">B</div>
          <div>
            <div className="check-brand-name">beti コミュニティ</div>
            <div className="check-brand-sub">mailing-list check</div>
          </div>
        </div>
        <a className="check-topbar-link" href={`mailto:${SUPPORT_EMAIL}`}>
          <I.Mail size={14} />
          <span className="check-topbar-link-text">{SUPPORT_EMAIL}</span>
        </a>
      </header>

      <main className="check-split">
        <section className="check-hero">
          <div className="check-hero-inner">
            <span className="check-hero-eyebrow">
              <span className="dot" />
              beti メルマガ配信チェック
            </span>
            <h1 className="check-hero-title">
              beti コミュニティ<br />
              サポートメルマガ<br />
              <em>配信システム</em>
            </h1>
            <p className="check-hero-sub">
              NFT 購入時にご利用いただいたメールアドレスを入力すると、
              beti メルマガ配信リストへの登録状況をその場で確認できます。
            </p>

            <div className="check-hero-illust">
              <img src="/check/community.jpg" alt="beti コミュニティのみんな" />
            </div>

            <div className="check-hero-meta">
              <span className="check-hero-meta-item">
                <I.Lock />
                入力情報はチェックにのみ使用します
              </span>
              <span className="check-hero-meta-item">
                <I.Sparkle />
                AI エージェントが即時応答
              </span>
            </div>
          </div>
        </section>

        <section className="check-form-panel">
          <div className="check-form-inner">
            <div className="check-form-head">
              <h1>配信されているか確認する</h1>
              <p>
                beti コミュニティで NFT 購入時にご利用いただいた
                <br />
                メールアドレスを入力してください。
              </p>
            </div>

            {!result && (
              <form onSubmit={submit} className="check-form-body">
                <div className="check-field">
                  <label className="check-field-label">
                    メールアドレス <span className="req">*</span>
                  </label>
                  <div className="check-input-wrap">
                    <I.Mail />
                    <input
                      ref={inputRef}
                      type="email"
                      inputMode="email"
                      autoComplete="email"
                      className="check-input"
                      placeholder="example@gmail.com"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        setError(null);
                      }}
                      autoFocus
                    />
                  </div>
                  <div className="check-field-hint">
                    大文字・小文字、半角・全角に注意してください。NFT 購入時と同じメールアドレスをご入力ください。
                  </div>
                </div>

                {error && (
                  <div className="check-form-error">
                    <I.AlertTriangle />
                    <span>{error}</span>
                  </div>
                )}

                <button type="submit" className="check-btn lg full" disabled={loading}>
                  {loading ? (
                    <>
                      <span className="spinner" /> 確認中…
                    </>
                  ) : (
                    <>
                      確認する <I.ArrowRight />
                    </>
                  )}
                </button>

                <div className="check-info-note">
                  <I.Info />
                  <span>
                    ご入力いただいたメールアドレスは、配信リストとの照合のみに利用し、当方では保存いたしません。
                  </span>
                </div>
              </form>
            )}

            {result && result.found && (
              <ResultOk result={result} onReset={reset} onToast={showToast} />
            )}
            {result && !result.found && (
              <ResultNotFound email={email} onReset={reset} onToast={showToast} />
            )}

            <div className="check-form-foot">
              <span>© 2026 beti コミュニティ運営</span>
              <span>
                <a href="#" onClick={(e) => e.preventDefault()}>プライバシー</a>
                <span style={{ margin: "0 6px", color: "var(--border-strong)" }}>·</span>
                <a href="#" onClick={(e) => e.preventDefault()}>利用規約</a>
              </span>
            </div>
          </div>
        </section>
      </main>

      <div className="check-toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`check-toast${t.isError ? " err" : ""}`}>
            {t.isError ? <I.AlertTriangle /> : <I.Check />}
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ResultOk({
  result,
  onReset,
  onToast,
}: {
  result: { found: true; name?: string; nft_types?: string[] };
  onReset: () => void;
  onToast: (msg: string, isError?: boolean) => void;
}) {
  const nfts = result.nft_types || [];
  return (
    <div className="check-result ok">
      <div className="check-result-head">
        <div className="ic">
          <I.CheckCircle />
        </div>
        <div style={{ flex: 1 }}>
          <h2>
            {result.name ? `${result.name} 様のご登録を確認しました` : "ご登録を確認しました"}
          </h2>
          <p>beti メルマガ配信は正常にお届けされます。安心してお待ちください。</p>
        </div>
      </div>
      <div className="check-result-body">
        {nfts.length > 0 && (
          <>
            <div>
              <div className="check-nft-label">ご購入の NFT</div>
              <div className="check-nft-list">
                {nfts.map((t) => (
                  <span key={t} className={`badge ${nftBadgeClass(t)}`}>
                    {nftLabel(t)}
                  </span>
                ))}
              </div>
            </div>
            <div className="check-divider" />
          </>
        )}

        <p>
          配信が届かない、登録内容にご不明な点がございましたら、
          下記のサポート窓口までお気軽にお問い合わせください。
        </p>

        <CopyableSupport email={SUPPORT_EMAIL} onToast={onToast} />

        <div className="check-ai-note">
          <I.Sparkle />
          <span>
            お問い合わせには beti 専用の AI エージェントが迅速にご返信いたします。
            判断に迷う内容は運営担当者（仁）が直接対応いたします。
          </span>
        </div>

        <div style={{ display: "flex", gap: 8, paddingTop: 6 }}>
          <button type="button" className="check-btn ghost" onClick={onReset}>
            <I.Refresh /> 別のアドレスで確認
          </button>
        </div>
      </div>
    </div>
  );
}

function ResultNotFound({
  email,
  onReset,
  onToast,
}: {
  email: string;
  onReset: () => void;
  onToast: (msg: string, isError?: boolean) => void;
}) {
  return (
    <div className="check-result notfound">
      <div className="check-result-head">
        <div className="ic">
          <I.AlertTriangle />
        </div>
        <div style={{ flex: 1 }}>
          <h2>該当する登録が見つかりませんでした</h2>
          <p style={{ marginTop: 6 }}>
            入力されたメールアドレス <code>{email}</code> は、現在の beti メルマガ配信リストに含まれていないようです。
          </p>
        </div>
      </div>
      <div className="check-result-body">
        <p style={{ fontWeight: 500, color: "var(--text)" }}>考えられる原因</p>
        <ul className="check-list">
          <li>
            <I.Tag /> NFT 購入時に別のメールアドレスを使用された
          </li>
          <li>
            <I.Tag /> 表記の違い（半角・全角、大文字・小文字、<code>+1</code> などのサブアドレス）
          </li>
          <li>
            <I.Tag /> 取込みが完了していない
          </li>
        </ul>

        <p>
          別のメールアドレスでお試しいただくか、お手数ですが下記までご連絡ください。
          事務局にて確認いたします。
        </p>

        <CopyableSupport email={SUPPORT_EMAIL} onToast={onToast} />

        <div style={{ display: "flex", gap: 8, paddingTop: 6, flexWrap: "wrap" }}>
          <button type="button" className="check-btn" onClick={onReset}>
            <I.ArrowLeft /> 別のアドレスで確認
          </button>
        </div>
      </div>
    </div>
  );
}

function CopyableSupport({
  email,
  onToast,
}: {
  email: string;
  onToast: (msg: string, isError?: boolean) => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(email);
      } else {
        const ta = document.createElement("textarea");
        ta.value = email;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      onToast(`${email} をコピーしました`);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      onToast("コピーに失敗しました", true);
    }
  }

  function onKey(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      copy();
    }
  }

  return (
    <div className="check-support">
      <I.Mail />
      <button
        type="button"
        className="check-support-email"
        onClick={copy}
        onKeyDown={onKey}
        title="クリックでコピー"
        aria-label={`${email} をコピー`}
      >
        {email}
      </button>
      <div className="check-support-actions">
        <button
          type="button"
          className={`check-support-btn${copied ? " copied" : ""}`}
          onClick={copy}
          aria-label="メールアドレスをコピー"
        >
          {copied ? (
            <>
              <I.Check /> コピー済み
            </>
          ) : (
            <>
              <I.Copy /> コピー
            </>
          )}
        </button>
        <a className="check-support-btn primary" href={`mailto:${email}`} aria-label="メールを送信">
          <I.Send /> 送信
        </a>
      </div>
    </div>
  );
}
