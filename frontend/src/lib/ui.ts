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
    case "cancelled": return { label: "キャンセル", cls: "badge-neutral" };
    case "scheduled": return { label: "予約済", cls: "badge-warning" };
    case "pending": return { label: "保留中", cls: "badge-warning" };
    case "waiting": return { label: "承認待ち", cls: "badge-warning" };
    case "running": return { label: "実行中", cls: "badge-info" };
    case "queued": return { label: "待機中", cls: "badge-neutral" };
    default: return { label: s || "不明", cls: "badge-neutral" };
  }
}

/**
 * Backend は UTC で保存しているが、TZ-naive な ISO 文字列も混在するため
 * 末尾に TZ 表記が無ければ Z を補って UTC として解釈する。
 */
function _parseIsoAsUtc(iso: string): Date {
  const hasTZ = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  return new Date(hasTZ ? iso : iso + "Z");
}

/**
 * UTC 保存値を JST (Asia/Tokyo) で "YYYY-MM-DD HH:mm" 表示。
 * 海外 PC からアクセスしても常に JST 基準で見える。
 */
export function fmtDate(iso?: string): string {
  if (!iso) return "-";
  const d = _parseIsoAsUtc(iso);
  if (isNaN(d.getTime())) return iso.replace("T", " ").substring(0, 16);
  const parts = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}`;
}

export function fmtDateShort(iso?: string): string {
  if (!iso) return "-";
  const d = _parseIsoAsUtc(iso);
  if (isNaN(d.getTime())) return iso.substring(0, 10);
  const parts = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "numeric", day: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value || "";
  return `${get("month")}/${get("day")} ${get("hour")}:${get("minute")}`;
}

/** ja-JP ローカライズ。海外 TZ の PC でも常に JST で表示。 */
export function fmtDateTimeJst(iso?: string): string {
  if (!iso) return "-";
  const d = _parseIsoAsUtc(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
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

const GMAIL_DOMAINS = new Set(["gmail.com", "googlemail.com"]);

/**
 * Gmail/Googlemail のドット違い・+タグ違いを 1 つの受信箱として
 * 扱うための正規化。バックエンド `members.canonical_inbox` と一致。
 */
export function canonicalInbox(email: string): string {
  if (!email) return "";
  const [local0, domain0] = email.trim().toLowerCase().split("@");
  if (!domain0) return email.trim().toLowerCase();
  const local = local0.split("+")[0];
  if (GMAIL_DOMAINS.has(domain0)) {
    return `${local.replace(/\./g, "")}@gmail.com`;
  }
  return `${local}@${domain0}`;
}

export function uniqueInboxCount(emails: Iterable<string>): number {
  const seen = new Set<string>();
  for (const e of emails) {
    const k = canonicalInbox(e);
    if (k) seen.add(k);
  }
  return seen.size;
}
