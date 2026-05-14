import type { Member } from "./types";

// バックエンドは Japanese names を NFT 種別キーとして使用。短縮ラベルを別途用意。
export const NFT_TYPES = [
  "会員権NFT",
  "パチスロホイホイNFT",
  "ラッキーマスタードNFT",
  "スペシャルマスタードNFT",
] as const;

export const NFT_LABELS: Record<string, string> = {
  "会員権NFT": "会員",
  "パチスロホイホイNFT": "パチ",
  "ラッキーマスタードNFT": "ラッキー",
  "スペシャルマスタードNFT": "スペシャル",
};

const NFT_BADGE_CLASS: Record<string, string> = {
  "会員権NFT": "badge-kaiin",
  "パチスロホイホイNFT": "badge-pachi",
  "ラッキーマスタードNFT": "badge-lucky",
  "スペシャルマスタードNFT": "badge-special",
};

export function nftBadgeClass(t?: string): string {
  return NFT_BADGE_CLASS[t || ""] || "badge-neutral";
}

export function nftLabel(t?: string): string {
  return NFT_LABELS[t || ""] || t || "不明";
}

export function statusInfo(s?: string): { label: string; cls: string } {
  switch (s) {
    case "sent": return { label: "送信済", cls: "badge-success" };
    case "auto_sent": return { label: "AI自動", cls: "badge-success" };
    case "approved": return { label: "承認済", cls: "badge-success" };
    case "approved_edited": return { label: "修正送信", cls: "badge-success" };
    case "done": return { label: "完了", cls: "badge-success" };
    case "error": return { label: "失敗", cls: "badge-danger" };
    case "failed": return { label: "失敗", cls: "badge-danger" };
    case "rejected": return { label: "却下", cls: "badge-danger" };
    case "pending": return { label: "保留中", cls: "badge-warning" };
    case "waiting": return { label: "承認待ち", cls: "badge-warning" };
    case "running": return { label: "実行中", cls: "badge-info" };
    case "queued": return { label: "待機中", cls: "badge-neutral" };
    default: return { label: s || "不明", cls: "badge-neutral" };
  }
}

export function fmtDate(iso?: string): string {
  if (!iso) return "-";
  return iso.replace("T", " ").substring(0, 16);
}

export function fmtDateShort(iso?: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso.substring(0, 10);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function debounce<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let t: ReturnType<typeof setTimeout> | undefined;
  return ((...a: any[]) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  }) as T;
}

export function memberInitial(m: Member): string {
  return (m.name?.[0] || m.email?.[0] || "?").toUpperCase();
}
