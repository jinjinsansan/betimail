"use client";
import { useState, FormEvent } from "react";
import { api } from "@/lib/api";
import { saveToken } from "@/lib/auth";

type Props = { onSuccess: () => void };

export default function Login({ onSuccess }: Props) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const r = await api.login(username, password);
      saveToken(r.token, r.expires_at);
      onSuccess();
    } catch (err: any) {
      setError(err.message || "ログインに失敗しました");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <h1>⚡ Betimail</h1>
        <div className="subtitle">NFTコミュニティ サポート管理</div>
        <label>ユーザー名</label>
        <input
          type="text" autoComplete="username"
          value={username} onChange={(e) => setUsername(e.target.value)}
          required
        />
        <label>パスワード</label>
        <input
          type="password" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <div className="error-msg">{error}</div>}
        <button type="submit" className="btn" disabled={loading}>
          {loading ? <><span className="spinner"></span> ログイン中…</> : "ログイン"}
        </button>
      </form>
    </div>
  );
}
