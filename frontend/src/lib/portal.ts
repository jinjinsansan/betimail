// ポータル（betiダッシュボード）専用の API クライアント。
// 管理者トークン (lib/auth.ts) / ラッキー会員トークン (lib/lucky.ts) とは別に、
// ポータル会員トークンを localStorage で管理する（互いに干渉しないようにするため）。

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

const TOKEN_KEY = "portal_token";

export function getPortalToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setPortalToken(token: string) {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearPortalToken() {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

export const PORTAL_NFT_LABELS: Record<string, string> = {
  MEMBER: "会員権NFT",
  HOIHOI: "パチスロホイホイNFT",
  SPECIAL_MUSTARD: "スペシャルマスタードNFT",
  LEADER: "リーダーNFT",
  DIGITAL_PACHISURO: "デジタルパチスロNFT",
};

export type PortalAsset = {
  nft_type: string;
  purchased_units: number;
  staked_units: number;
  transferred_in: number;
  transferred_out: number;
  unstaked_units: number;
};

export type BuybackRow = {
  id: number;
  nft_type: string;
  units: number | null;
  status: string; // pending / confirmed / processing / paid / rejected
  requested_at: string;
  action_at?: string | null;
};

export type WithdrawalRow = {
  id: number;
  amount: number;
  destination: string;
  status: string; // pending / processing / paid / rejected / cancelled
  requested_at: string;
  action_at?: string | null;
};

export type LegacyWithdrawalRow = {
  external_id: number;
  amount_usdt: number;
  destination: string | null;
  status: number; // 0=申請中 1=処理中 2=完了 3=却下
  requested_at: string | null;
  action_at?: string | null;
};

export type PortalRewardRow = {
  nft_type: string | null;
  amount: number;
  units: number | null;
  balance_after: number | null;
  rewarded_at: string;
};

export type PortalDashboard = {
  email: string;
  name?: string | null;
  wallet_address?: string | null;
  balance: number;
  cumulative_reward: number;
  assets: PortalAsset[];
  buybacks: BuybackRow[];
  withdrawals: WithdrawalRow[];
  legacy_withdrawals: LegacyWithdrawalRow[];
  history: PortalRewardRow[];
};

export class PortalApiError extends Error {
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
    const t = getPortalToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || j.error || detail;
    } catch {}
    throw new PortalApiError(detail, res.status);
  }
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export const portalApi = {
  login: (email: string) =>
    call<{
      found?: boolean;
      verification_required?: boolean;
      masked_email?: string;
      expires_in?: number;
    }>("/api/portal/login", { method: "POST", body: JSON.stringify({ email }) }),

  verify: (email: string, code: string) =>
    call<{ token: string; expires_at: number; dashboard: PortalDashboard }>(
      "/api/portal/verify",
      { method: "POST", body: JSON.stringify({ email, code }) }
    ),

  me: () => call<PortalDashboard>("/api/portal/me", {}, true),

  stake: (nft_type: string) =>
    call<{ staked: number; dashboard: PortalDashboard }>(
      "/api/portal/stake",
      { method: "POST", body: JSON.stringify({ nft_type }) },
      true
    ),

  buyback: () =>
    call<{ id: number; dashboard: PortalDashboard }>(
      "/api/portal/buyback",
      { method: "POST", body: JSON.stringify({ nft_type: "HOIHOI", confirm: true }) },
      true
    ),

  withdraw: (amount: number, destination: string) =>
    call<{ id: number; dashboard: PortalDashboard }>(
      "/api/portal/withdraw",
      { method: "POST", body: JSON.stringify({ amount, destination }) },
      true
    ),

  cancelWithdraw: (id: number) =>
    call<{ ok: boolean; dashboard: PortalDashboard }>(
      `/api/portal/withdraw/${id}`,
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

export const BUYBACK_STATUS_LABELS: Record<string, string> = {
  pending: "申請受付",
  confirmed: "運営確認済み",
  processing: "処理中",
  paid: "支払い完了",
  rejected: "却下",
};

export const WITHDRAWAL_STATUS_LABELS: Record<string, string> = {
  pending: "申請中",
  processing: "処理中",
  paid: "支払い完了",
  rejected: "却下",
  cancelled: "取り下げ",
};

export const LEGACY_WD_STATUS_LABELS: Record<number, string> = {
  0: "申請中",
  1: "処理中",
  2: "完了",
  3: "却下",
};
