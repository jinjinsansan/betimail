// 白のダッシュボード（afi.irah.uk 再構築）専用の API クライアント。
// 他のトークン（管理者 / lucky / portal）とは別に white_token を localStorage で管理する。

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

const TOKEN_KEY = "white_token";

export function getWhiteToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setWhiteToken(token: string) {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearWhiteToken() {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

export type WhiteWithdrawalRow = {
  id: number;
  amount: number;
  destination: string;
  status: string; // pending / processing / paid / rejected / cancelled
  requested_at: string;
  action_at?: string | null;
};

export type WhiteLegacyWithdrawalRow = {
  external_id: number;
  amount_usdt: number;
  destination: string | null;
  status: number; // afi: 1=未承認 2=承認済
  requested_at: string | null;
  action_at?: string | null;
};

export type WhiteDashboard = {
  email: string;
  name?: string | null;
  wallet_address?: string | null;
  balance: number;
  kaiin_units: number;
  hoihoi_units: number;
  snapshot_at?: string | null;
  withdrawals: WhiteWithdrawalRow[];
  legacy_withdrawals: WhiteLegacyWithdrawalRow[];
};

export class WhiteApiError extends Error {
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
    const t = getWhiteToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || j.error || detail;
    } catch {}
    throw new WhiteApiError(detail, res.status);
  }
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export const whiteApi = {
  login: (email: string) =>
    call<{
      found?: boolean;
      verification_required?: boolean;
      masked_email?: string;
      expires_in?: number;
    }>("/api/white/login", { method: "POST", body: JSON.stringify({ email }) }),

  verify: (email: string, code: string) =>
    call<{ token: string; expires_at: number; dashboard: WhiteDashboard }>(
      "/api/white/verify",
      { method: "POST", body: JSON.stringify({ email, code }) }
    ),

  me: () => call<WhiteDashboard>("/api/white/me", {}, true),

  withdraw: (amount: number, destination: string) =>
    call<{ id: number; dashboard: WhiteDashboard }>(
      "/api/white/withdraw",
      { method: "POST", body: JSON.stringify({ amount, destination }) },
      true
    ),

  cancelWithdraw: (id: number) =>
    call<{ ok: boolean; dashboard: WhiteDashboard }>(
      `/api/white/withdraw/${id}`,
      { method: "DELETE" },
      true
    ),
};

export function fmtUsdt(n: number | null | undefined): string {
  const v = Number(n || 0);
  return v.toLocaleString("ja-JP", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.slice(0, 10);
  const [y, m, day] = d.split("-");
  return m && day ? `${y}/${Number(m)}/${Number(day)}` : d;
}

export const WHITE_WD_STATUS_LABELS: Record<string, string> = {
  pending: "申請中",
  processing: "処理中",
  paid: "支払い完了",
  rejected: "却下",
  cancelled: "取り下げ",
};

export const WHITE_LEGACY_WD_STATUS_LABELS: Record<number, string> = {
  1: "未承認",
  2: "承認済み",
};
