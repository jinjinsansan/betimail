import csv
import os
import re
import threading
from typing import Optional
from config import MEMBERS_CSV_PATH, NFT_TYPES
from logging_config import get_logger

log = get_logger(__name__)

_FIELDS = ["name", "email", "nft_type", "joined_date", "notes"]
_lock = threading.RLock()
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_nft_type_field(nft_type: str) -> str:
    raw = [t.strip() for t in (nft_type or "").split(",") if t.strip()]
    if not raw:
        raise ValueError("NFT種別は必須です")
    unknown = [t for t in raw if t not in NFT_TYPES]
    if unknown:
        raise ValueError(f"不正なNFT種別: {', '.join(unknown)}")
    ordered = []
    for t in NFT_TYPES:
        if t in raw and t not in ordered:
            ordered.append(t)
    return ", ".join(ordered)


def _ensure_csv() -> None:
    if not os.path.exists(MEMBERS_CSV_PATH):
        os.makedirs(os.path.dirname(MEMBERS_CSV_PATH), exist_ok=True)
        with open(MEMBERS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


_GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def canonical_inbox(email: str) -> str:
    """同一の物理受信箱に届く別表記アドレスを 1 つにまとめた正規形を返す。

    - 大文字/小文字を無視
    - Gmail/Googlemail は `+tag` を除去し、ローカル部のドットを除去
    - その他プロバイダは `+tag` のみ除去（大半の主要プロバイダで実態に合う）

    送信時の重複排除キーとして使う。DB の生 email は変更しない。
    """
    if not email:
        return ""
    local, _, domain = email.strip().lower().partition("@")
    if not domain:
        return email.strip().lower()
    local = local.split("+", 1)[0]
    if domain in _GMAIL_DOMAINS:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def dedupe_by_inbox(members: list[dict]) -> list[dict]:
    """正規化された受信箱単位で重複を除外。

    各受信箱について、NFT種別が最も多い（=最も情報量の多い）レコードを採用。
    同点の場合は最後に追加された（=新しい）方を優先。
    """
    by_inbox: dict[str, dict] = {}
    for m in members:
        key = canonical_inbox(m.get("email", ""))
        if not key:
            continue
        existing = by_inbox.get(key)
        if existing is None:
            by_inbox[key] = m
            continue
        # NFT種別が多い方を優先
        cur_n = len((existing.get("nft_type") or "").split(","))
        new_n = len((m.get("nft_type") or "").split(","))
        if new_n >= cur_n:
            by_inbox[key] = m
    return list(by_inbox.values())


def _validate(name: str, email: str, nft_type: str, joined_date: str) -> str:
    if not name.strip():
        raise ValueError("名前は必須です")
    if not _EMAIL_RE.match(email):
        raise ValueError(f"メールアドレスの形式が不正です: {email}")
    normalized_nft = _normalize_nft_type_field(nft_type)
    if joined_date and not _DATE_RE.match(joined_date):
        raise ValueError(f"日付は YYYY-MM-DD 形式で指定してください: {joined_date}")
    return normalized_nft


def get_all_members() -> list[dict]:
    with _lock:
        _ensure_csv()
        with open(MEMBERS_CSV_PATH, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))


def get_members_by_nft_type(nft_type: str) -> list[dict]:
    """nft_type を含む（カンマ区切りで複数保有の場合に対応）。"""
    return [
        m for m in get_all_members()
        if nft_type in [t.strip() for t in (m.get("nft_type") or "").split(",")]
    ]


def get_members_by_segment(segment: str) -> list[dict]:
    """名前付きセグメントで絞り込む。

    - lucky_only: ラッキーマスタードNFT保有 かつ スペシャル非保有 (135名想定)
    - lucky_and_special: ラッキー かつ スペシャル両方保有 (259名想定)
    """
    def types(m: dict) -> set[str]:
        return {t.strip() for t in (m.get("nft_type") or "").split(",") if t.strip()}

    all_members = get_all_members()
    if segment == "lucky_only":
        return [m for m in all_members
                if "ラッキーマスタードNFT" in types(m) and "スペシャルマスタードNFT" not in types(m)]
    if segment == "lucky_and_special":
        t = "ラッキーマスタードNFT"
        s = "スペシャルマスタードNFT"
        return [m for m in all_members if t in types(m) and s in types(m)]
    return []


def get_member_by_email(email: str) -> Optional[dict]:
    target = _normalize_email(email)
    for m in get_all_members():
        if _normalize_email(m["email"]) == target:
            return m
    return None


def add_member(name: str, email: str, nft_type: str, joined_date: str, notes: str = "") -> dict:
    name = name.strip()
    email = email.strip()
    nft_type = _validate(name, email, nft_type, joined_date)
    with _lock:
        existing = get_member_by_email(email)
        if existing:
            raise ValueError(f"このメールアドレスは既に登録されています: {email}")
        member = {
            "name": name, "email": email, "nft_type": nft_type,
            "joined_date": joined_date, "notes": notes,
        }
        _ensure_csv()
        with open(MEMBERS_CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writerow(member)
        log.info("Added member: %s <%s> [%s]", name, email, nft_type)
        return member


def delete_member(email: str) -> bool:
    target = _normalize_email(email)
    with _lock:
        members = get_all_members()
        new_members = [m for m in members if _normalize_email(m["email"]) != target]
        if len(new_members) == len(members):
            return False
        with open(MEMBERS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(new_members)
        log.info("Deleted member: %s", email)
        return True


def update_member(email: str, **kwargs) -> Optional[dict]:
    target = _normalize_email(email)
    with _lock:
        members = get_all_members()
        updated = None
        for m in members:
            if _normalize_email(m["email"]) == target:
                # 更新前にバリデーション
                merged = {**m, **{k: v for k, v in kwargs.items() if k in _FIELDS and v is not None}}
                merged["nft_type"] = _validate(
                    merged["name"], merged["email"], merged["nft_type"], merged.get("joined_date", ""),
                )
                # メールアドレスを変更しようとしている場合、重複チェック
                if _normalize_email(merged["email"]) != target:
                    if any(_normalize_email(o["email"]) == _normalize_email(merged["email"])
                           for o in members if o is not m):
                        raise ValueError(f"このメールアドレスは既に使われています: {merged['email']}")
                m.update(merged)
                updated = m
        if updated is None:
            return None
        with open(MEMBERS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(members)
        log.info("Updated member: %s", email)
        return updated


def import_csv(file_content: str) -> dict:
    """CSV文字列を取り込んで、重複・形式エラーをスキップしつつ追加する。"""
    import io
    reader = csv.DictReader(io.StringIO(file_content))
    added = 0
    skipped: list[dict] = []
    for row in reader:
        try:
            add_member(
                name=row.get("name", ""),
                email=row.get("email", ""),
                nft_type=row.get("nft_type", ""),
                joined_date=row.get("joined_date", ""),
                notes=row.get("notes", ""),
            )
            added += 1
        except ValueError as e:
            skipped.append({"row": row, "reason": str(e)})
    return {"added": added, "skipped": skipped}


def export_csv() -> str:
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_FIELDS)
    writer.writeheader()
    writer.writerows(get_all_members())
    return buf.getvalue()
