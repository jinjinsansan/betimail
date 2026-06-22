// ラッキーマスタード会員ポータル専用の API クライアント。
// 管理者トークン (lib/auth.ts) とは別に、会員トークンを localStorage で管理する
// （管理者ログインと会員ログインが互いに干渉しないようにするため）。

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

const TOKEN_KEY = "lucky_token";

export function getLuckyToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setLuckyToken(token: string) {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearLuckyToken() {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

export type RewardRow = {
  amount: number;
  nft_count: number | null;
  balance_after: number | null;
  rewarded_at: string;
};

export type LuckyDashboard = {
  email: string;
  name?: string | null;
  nft_count: number;
  owned_nft: number;
  balance: number;
  cumulative_reward: number;
  today_reward: number;
  rate: number;
  last_reward_at?: string | null;
  history: RewardRow[];
  series: { date: string; amount: number; balance_after: number | null }[];
};

export class LuckyApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function call<T>(path: string, init: RequestInit = {}, withAuth = false): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (init.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (withAuth) {
    const t = getLuckyToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || j.error || detail;
    } catch {}
    throw new LuckyApiError(detail, res.status);
  }
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export const luckyApi = {
  login: (email: string) =>
    call<{
      found?: boolean;
      verification_required?: boolean;
      masked_email?: string;
      expires_in?: number;
    }>("/api/lucky/login", { method: "POST", body: JSON.stringify({ email }) }),

  verify: (email: string, code: string) =>
    call<{ token: string; expires_at: number; dashboard: LuckyDashboard }>(
      "/api/lucky/verify",
      { method: "POST", body: JSON.stringify({ email, code }) }
    ),

  me: () => call<LuckyDashboard>("/api/lucky/me", {}, true),
};

export function fmtUsdt(n: number | null | undefined): string {
  const v = Number(n || 0);
  return v.toLocaleString("ja-JP", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.slice(0, 10); // YYYY-MM-DD
  const [, m, day] = d.split("-");
  return m && day ? `${Number(m)}/${Number(day)}` : d;
}
