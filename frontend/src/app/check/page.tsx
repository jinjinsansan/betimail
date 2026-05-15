"use client";
import { useState, FormEvent } from "react";
import { api } from "@/lib/api";
import { I } from "@/lib/icons";
import { nftBadgeClass } from "@/lib/ui";

type Result = {
  found: boolean;
  name?: string;
  nft_types?: string[];
} | null;

export default function CheckPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    if (!email.trim() || !email.includes("@")) {
      setError("メールアドレスを正しく入力してください");
      return;
    }
    setLoading(true);
    try {
      const r = await api.publicCheck(email.trim().toLowerCase());
      setResult(r);
    } catch (e: any) {
      setError(e.message || "確認に失敗しました。少し時間をおいてお試しください。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="check-shell">
      <div className="check-card">
        <div className="check-header">
          <div className="brand-mark">B</div>
          <h1 className="check-title">beti メルマガ配信チェックページ</h1>
          <p className="check-sub">
            ご自身のメールアドレスが beti メルマガ配信リストに正しく登録されているか、
            ここでご確認いただけます。
          </p>
        </div>

        <form onSubmit={submit} className="check-form">
          <label>メールアドレス</label>
          <p className="check-hint">
            beti コミュニティで NFT 購入時にご利用いただいたメールアドレスを入力してください。
          </p>
          <input
            type="email"
            className="input"
            placeholder="example@gmail.com"
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            autoComplete="email"
            autoFocus
          />
          <button type="submit" className="btn primary lg check-submit" disabled={loading}>
            {loading ? <><span className="spinner" /> 確認中…</> : <>確認する <I.ArrowRight /></>}
          </button>
        </form>

        {error && (
          <div className="check-error">
            <I.AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}

        {result && result.found && (
          <div className="check-result check-ok">
            <div className="check-result-head">
              <I.CheckCircle />
              <h2>{result.name || "ご登録"} が確認できました。</h2>
            </div>
            <p className="check-result-body">
              {(result.nft_types || []).length > 0
                ? `${result.name || "あなた"} 様は以下の NFT をご購入されておられます：`
                : "メルマガ配信リストへの登録を確認しました。"}
            </p>
            <div className="check-nft-list">
              {(result.nft_types || []).map((t) => (
                <span key={t} className={`badge ${nftBadgeClass(t)}`}>{t}</span>
              ))}
              {(!result.nft_types || result.nft_types.length === 0) && (
                <span style={{ color: "var(--text-3)", fontSize: 13 }}>
                  ご購入記録の詳細は事務局にて確認させていただきます。
                </span>
              )}
            </div>
            <div className="check-confirm">
              <p>
                <b>beti メルマガ配信は正常に配信されますので、ご安心ください。</b>
              </p>
              <p>
                配信が届かない・登録内容にご不明な点がございましたら、いつでも以下のメールアドレスまでお問い合わせください。
              </p>
              <div className="check-support">
                <I.Mail />
                <a href="mailto:support@betimail.uk">support@betimail.uk</a>
              </div>
              <p className="check-ai-note">
                ※ お問い合わせには beti 専用の AI エージェントが迅速にご返信いたします。
                判断に迷う内容は運営担当者（仁）が直接対応いたします。
              </p>
            </div>
          </div>
        )}

        {result && !result.found && (
          <div className="check-result check-not-found">
            <div className="check-result-head">
              <I.AlertTriangle />
              <h2>該当する登録が見つかりませんでした</h2>
            </div>
            <p className="check-result-body">
              入力されたメールアドレス <code>{email}</code> は、現在の beti メルマガ配信リストに見つかりませんでした。
            </p>
            <p className="check-result-body" style={{ marginTop: 12 }}>
              以下の可能性があります：
            </p>
            <ul className="check-list">
              <li>NFT 購入時に別のメールアドレスを使用された</li>
              <li>メールアドレスの表記が違う（半角・全角、大文字・小文字、`+1` などのサブアドレス）</li>
              <li>取込が完了していない</li>
            </ul>
            <div className="check-confirm">
              <p>
                お手数ですが、別のメールアドレスでお試しいただくか、下記までご連絡ください。
                事務局にて確認させていただきます。
              </p>
              <div className="check-support">
                <I.Mail />
                <a href="mailto:support@betimail.uk">support@betimail.uk</a>
              </div>
            </div>
          </div>
        )}

        <div className="check-footer">
          <span>© 2026 beti コミュニティ運営</span>
        </div>
      </div>
    </div>
  );
}
