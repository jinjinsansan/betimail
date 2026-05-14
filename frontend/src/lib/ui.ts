import type { Member } from "./types";

export const NFT_BADGE: Record<string, string> = {
  "会員権NFT": "kaiin",
  "パチスロホイホイNFT": "pachi",
  "ラッキーマスタードNFT": "lucky",
  "スペシャルマスタードNFT": "special",
};

export const STATUS_LABEL: Record<string, { dot: string; text: string }> = {
  pending: { dot: "dot-pending", text: "処理中" },
  waiting: { dot: "dot-pending", text: "承認待ち" },
  approved: { dot: "dot-sent", text: "承認済み" },
  approved_edited: { dot: "dot-sent", text: "修正送信" },
  auto_sent: { dot: "dot-sent", text: "AI自動送信" },
  rejected: { dot: "dot-error", text: "却下" },
  sent: { dot: "dot-sent", text: "送信済み" },
  error: { dot: "dot-error", text: "エラー" },
};

export function fmtDate(iso?: string): string {
  if (!iso) return "-";
  return iso.replace("T", " ").substring(0, 16);
}

export function nftBadgeClass(t?: string): string {
  return NFT_BADGE[t || ""] || "unknown";
}

export function statusBadge(status?: string): { dot: string; text: string } {
  return STATUS_LABEL[status || ""] || { dot: "dot-pending", text: status || "-" };
}

export function memberDisplay(m: Member): string {
  return `${m.name} <${m.email}>`;
}

export function debounce<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let t: ReturnType<typeof setTimeout> | undefined;
  return ((...a: any[]) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  }) as T;
}
