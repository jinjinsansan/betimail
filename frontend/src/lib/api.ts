import { getToken, clearToken } from "./auth";
import type {
  Member, Template, Approval, BulkJob, Paged, SentEmail, ReceivedEmail,
  Health, LoginResponse, MemberHistory, MemberPurchases,
  WithdrawsList, WithdrawStats, MemberWithdrawSummary,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.body && !(init.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("betimail:unauthorized"));
    }
    throw new ApiError("認証エラー", 401);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || j.error || detail;
    } catch {}
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export const api = {
  health: () => request<Health>("/health"),
  login: (username: string, password: string) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  check: () => request<{ username: string; ok: boolean }>("/api/auth/check"),
  publicCheck: (email: string) =>
    request<{ found: boolean; name?: string; nft_types?: string[] }>("/api/public/check", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  nftTypes: () => request<string[]>("/api/nft-types"),

  members: {
    list: (nftType?: string) =>
      request<Member[]>(`/api/members${nftType ? `?nft_type=${encodeURIComponent(nftType)}` : ""}`),
    add: (m: Omit<Member, "notes"> & { notes?: string }) =>
      request<Member>("/api/members", { method: "POST", body: JSON.stringify(m) }),
    update: (email: string, m: Partial<Member>) =>
      request<Member>(`/api/members/${encodeURIComponent(email)}`, {
        method: "PUT", body: JSON.stringify(m),
      }),
    remove: (email: string) =>
      request<{ status: string }>(`/api/members/${encodeURIComponent(email)}`, { method: "DELETE" }),
    history: (email: string) =>
      request<MemberHistory>(`/api/members/${encodeURIComponent(email)}/history`),
    purchases: (email: string) =>
      request<MemberPurchases>(`/api/members/${encodeURIComponent(email)}/purchases`),
    withdraws: (email: string) =>
      request<MemberWithdrawSummary>(`/api/members/${encodeURIComponent(email)}/withdraws`),
    importCsv: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return request<{ added: number; skipped: { row: any; reason: string }[] }>(
        "/api/members/import", { method: "POST", body: fd },
      );
    },
    exportUrl: () => `${API_BASE}/api/members/export.csv`,
  },

  send: {
    bulk: (params: {
      nft_types: string[];
      subject: string;
      body: string;
      segment?: string | null;
      confirm_all?: boolean;
    }) =>
      request<{ status: string; job_id: number; count: number }>("/api/send", {
        method: "POST", body: JSON.stringify(params),
      }),
    jobs: () => request<BulkJob[]>("/api/send/jobs"),
    job: (id: number) => request<BulkJob>(`/api/send/jobs/${id}`),
  },

  preview: (body: string, sample?: Partial<Member>) =>
    request<{ rendered: string; sample: any }>("/api/preview", {
      method: "POST", body: JSON.stringify({ body, sample: sample || {} }),
    }),

  emails: {
    sent: (limit = 25, offset = 0, search = "") =>
      request<Paged<SentEmail>>(`/api/emails/sent?limit=${limit}&offset=${offset}&search=${encodeURIComponent(search)}`),
    received: (limit = 25, offset = 0, search = "") =>
      request<Paged<ReceivedEmail>>(`/api/emails/received?limit=${limit}&offset=${offset}&search=${encodeURIComponent(search)}`),
  },

  approvals: {
    list: () => request<Approval[]>("/api/approvals"),
    get: (id: number) => request<Approval>(`/api/approvals/${id}`),
    approve: (id: number) =>
      request<{ status: string }>(`/api/approvals/${id}/approve`, { method: "POST", body: JSON.stringify({}) }),
    edit: (id: number, body: string) =>
      request<{ status: string }>(`/api/approvals/${id}/edit`, { method: "POST", body: JSON.stringify({ body }) }),
    reject: (id: number) =>
      request<{ status: string }>(`/api/approvals/${id}/reject`, { method: "POST", body: JSON.stringify({}) }),
  },

  withdraws: {
    list: (limit = 500, email?: string) =>
      request<WithdrawsList>(`/api/withdraws?limit=${limit}${email ? `&email=${encodeURIComponent(email)}` : ""}`),
    stats: () => request<WithdrawStats>("/api/withdraws/stats"),
  },

  templates: {
    list: () => request<Template[]>("/api/templates"),
    upsert: (name: string, subject: string, body: string) =>
      request<{ id: number }>("/api/templates", {
        method: "POST", body: JSON.stringify({ name, subject, body }),
      }),
    remove: (id: number) =>
      request<{ status: string }>(`/api/templates/${id}`, { method: "DELETE" }),
  },
};
