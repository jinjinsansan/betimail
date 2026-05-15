"""beti コミュニティの保有者管理 CSV を読み込み、purchases テーブルに格納する。

人間管理用の横長 CSV（日次配布列が大量に付いている）から、コア列だけ抜き出して
DB に正規化する。同時に members.csv も再生成する。

使い方:
    # ドライラン（DBに書き込まず集計だけ）
    python tools/import_purchases.py --dry-run \
        --file "PH管理  - 購入者管理.csv:パチスロホイホイNFT" \
        --file "会員権管理 - デイリー配布作業管理シート.csv:会員権NFT"

    # 本番取り込み（既存 purchases を全削除して再投入）
    python tools/import_purchases.py --replace \
        --file "PH管理  - 購入者管理.csv:パチスロホイホイNFT" \
        --file "会員権管理 - デイリー配布作業管理シート.csv:会員権NFT"
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Optional

# プロジェクトルートをパス追加
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
JPY_RE = re.compile(r"[¥$,\s]")  # CSVの「¥1,000」表記を剥がす。実態は USDT 額


def parse_jpy(s: str) -> Optional[int]:
    if not s:
        return None
    s = JPY_RE.sub("", s).strip()
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except Exception:
            return None


def parse_float(s: str) -> Optional[float]:
    if not s:
        return None
    s = JPY_RE.sub("", s).strip()
    try:
        return float(s)
    except Exception:
        return None


def parse_int(s: str) -> Optional[int]:
    if not s:
        return None
    s = JPY_RE.sub("", s).strip()
    try:
        return int(float(s))
    except Exception:
        return None


def normalize_date(s: str) -> str:
    """'2024/01/16 23:09' → '2024-01-16'"""
    if not s:
        return ""
    s = s.strip().split(" ")[0]  # 時刻部分を捨てる
    s = s.replace("/", "-")
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def detect_format(headers: list[str]) -> str:
    """CSV 形式を判定。'ph' (パチスロホイホイ管理) or 'kaiin' (会員権管理) or 'unknown'。"""
    h = [c.strip() for c in headers[:10]]
    # PH管理:    チーム名, 名前, メールアドレス, 購入金額, 状態, 口数, 品番, 購入日, 配布完了, ...
    # 会員権管理: チーム, 名前, メールアドレス, アクティブ確認, 購入NFT金額, 現在の還元金額, 口数, トランザクションID, 購入日, 2日後払出日, 配布完了, ...
    if len(h) >= 8 and "購入金額" in h[:5] and "状態" in h[:5]:
        return "ph"
    if len(h) >= 9 and "アクティブ確認" in h[:5]:
        return "kaiin"
    return "unknown"


def parse_row_ph(row: list[str], nft_type: str, source_file: str) -> Optional[dict]:
    """PH管理 形式: チーム名, 名前, メール, 購入金額, 状態, 口数, 品番, 購入日, 配布完了, ..."""
    if len(row) < 8:
        return None
    email = row[2].strip().lower()
    if not email or not EMAIL_RE.match(email):
        return None
    return {
        "email": email,
        "name": row[1].strip(),
        "nft_type": nft_type,
        "amount_jpy": parse_jpy(row[3]),
        "units": parse_int(row[5]),
        "team": row[0].strip(),
        "transaction_id": row[6].strip(),
        "purchased_at": normalize_date(row[7]),
        "status": row[4].strip(),
        "returns_usdt": None,  # PH 管理にはまだ還元なし
        "source_file": source_file,
    }


def parse_row_kaiin(row: list[str], nft_type: str, source_file: str) -> Optional[dict]:
    """会員権管理 形式: チーム, 名前, メール, アクティブ確認, 購入NFT金額, 現在の還元金額, 口数, トランザクションID, 購入日, ..."""
    if len(row) < 9:
        return None
    email = row[2].strip().lower()
    if not email or not EMAIL_RE.match(email):
        return None
    return {
        "email": email,
        "name": row[1].strip(),
        "nft_type": nft_type,
        "amount_jpy": parse_jpy(row[4]),
        "units": parse_int(row[6]),
        "team": row[0].strip(),
        "transaction_id": row[7].strip(),
        "purchased_at": normalize_date(row[8]),
        "status": row[3].strip(),
        "returns_usdt": parse_float(row[5]),
        "source_file": source_file,
    }


def load_csv(path: str, nft_type: str) -> tuple[list[dict], str]:
    """CSV を読み込み、(records, format_name) を返す。"""
    records: list[dict] = []
    source_file = os.path.basename(path)
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            return [], "empty"
        fmt = detect_format(headers)
        if fmt == "unknown":
            raise ValueError(f"未対応の CSV 形式: {path}")
        parser = parse_row_ph if fmt == "ph" else parse_row_kaiin
        for row in reader:
            if not any(c.strip() for c in row):
                continue
            rec = parser(row, nft_type, source_file)
            if rec:
                records.append(rec)
    return records, fmt


def summarize(records: list[dict]) -> dict:
    by_nft: dict[str, dict] = defaultdict(lambda: {
        "rows": 0, "emails": set(), "total_jpy": 0, "total_units": 0, "total_returns": 0.0,
    })
    all_emails = set()
    for r in records:
        nft = r["nft_type"]
        b = by_nft[nft]
        b["rows"] += 1
        b["emails"].add(r["email"])
        all_emails.add(r["email"])
        if r.get("amount_jpy"):
            b["total_jpy"] += r["amount_jpy"]
        if r.get("units"):
            b["total_units"] += r["units"]
        if r.get("returns_usdt"):
            b["total_returns"] += r["returns_usdt"]
    return {
        "total_rows": len(records),
        "unique_emails": len(all_emails),
        "by_nft": {k: {
            "rows": v["rows"],
            "unique_emails": len(v["emails"]),
            "total_jpy": v["total_jpy"],
            "total_units": v["total_units"],
            "total_returns_usdt": round(v["total_returns"], 2),
        } for k, v in by_nft.items()},
    }


def regenerate_members_csv(records: list[dict], output_path: str) -> dict:
    """購入レコードをメール単位に集約し、members.csv を再生成する。"""
    by_email: dict[str, dict] = {}
    for r in records:
        e = r["email"]
        m = by_email.setdefault(e, {
            "name": r.get("name", ""),
            "email": e,
            "nft_types": set(),
            "joined_date": r.get("purchased_at", ""),
            "notes_parts": [],
            "total_jpy": 0,
            "total_units": 0,
            "total_returns": 0.0,
        })
        m["nft_types"].add(r["nft_type"])
        # 名前は最初に拾ったものを優先（CSV では複数行に同じ名前のことが多い）
        if not m["name"] and r.get("name"):
            m["name"] = r["name"]
        if r.get("purchased_at") and (not m["joined_date"] or r["purchased_at"] < m["joined_date"]):
            m["joined_date"] = r["purchased_at"]
        if r.get("amount_jpy"):
            m["total_jpy"] += r["amount_jpy"]
        if r.get("units"):
            m["total_units"] += r["units"]
        if r.get("returns_usdt"):
            m["total_returns"] += r["returns_usdt"]

    rows = []
    for email, m in sorted(by_email.items()):
        # NFT種別はカンマ区切りで列挙
        nft_list = ", ".join(sorted(m["nft_types"]))
        # notes に投資サマリーを構造化テキストで残す
        notes = f"投資合計: ${m['total_jpy']:,} USDT / 口数: {m['total_units']} / 還元累計: {m['total_returns']:.2f} USDT"
        rows.append({
            "name": m["name"] or "(名前未設定)",
            "email": email,
            "nft_type": nft_list,
            "joined_date": m["joined_date"],
            "notes": notes,
        })

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "nft_type", "joined_date", "notes"])
        writer.writeheader()
        writer.writerows(rows)

    return {"members_written": len(rows), "path": output_path}


def main():
    p = argparse.ArgumentParser(description="CSV を読み込み purchases テーブルに取り込む")
    p.add_argument(
        "--file",
        action="append",
        required=True,
        help='形式: "ファイルパス:NFT種別" （例: "PH管理.csv:パチスロホイホイNFT"）',
    )
    p.add_argument("--dry-run", action="store_true", help="DBに書き込まず集計だけ")
    p.add_argument("--replace", action="store_true", help="purchases を全削除してから取り込む")
    p.add_argument("--members-csv", default=os.path.join(ROOT, "data", "members.csv"),
                   help="再生成する members.csv の出力先")
    p.add_argument("--no-members-csv", action="store_true", help="members.csv は再生成しない")
    args = p.parse_args()

    all_records: list[dict] = []
    for spec in args.file:
        if ":" not in spec:
            print(f"❌ --file は 'パス:NFT種別' 形式: {spec}", file=sys.stderr)
            sys.exit(1)
        path, nft_type = spec.rsplit(":", 1)
        path = path.strip()
        nft_type = nft_type.strip()
        if not os.path.exists(path):
            print(f"❌ ファイルが見つかりません: {path}", file=sys.stderr)
            sys.exit(1)
        print(f"📥 読み込み: {path} → {nft_type}")
        records, fmt = load_csv(path, nft_type)
        print(f"   形式: {fmt} / 有効レコード: {len(records)} 件")
        all_records.extend(records)

    print()
    summary = summarize(all_records)
    print("=" * 60)
    print(f"📊 集計サマリー")
    print(f"  総レコード数 (購入行): {summary['total_rows']}")
    print(f"  ユニークメール数: {summary['unique_emails']}")
    print()
    for nft, stats in summary["by_nft"].items():
        print(f"  ◆ {nft}")
        print(f"    - 行数: {stats['rows']}")
        print(f"    - ユニーク保有者: {stats['unique_emails']}")
        print(f"    - 投資合計: ${stats['total_jpy']:,} USDT")
        print(f"    - 口数合計: {stats['total_units']}")
        print(f"    - 還元累計: {stats['total_returns_usdt']} USDT")
        print()

    if args.dry_run:
        print("🟡 dry-run のため DB / members.csv への書き込みはスキップしました")
        return

    # 実取り込み
    import db
    db.init_db()
    if args.replace:
        deleted = db.clear_purchases()
        print(f"🗑️  既存 purchases を {deleted} 件削除")
    inserted = db.bulk_insert_purchases(all_records)
    print(f"✅ purchases に {inserted} 件挿入")
    print(f"   全体: {db.count_purchases()} 件 / ユニークメール {db.distinct_emails_in_purchases()}")

    if not args.no_members_csv:
        res = regenerate_members_csv(all_records, args.members_csv)
        print(f"📝 members.csv を再生成: {res['path']} ({res['members_written']} 名)")


if __name__ == "__main__":
    main()
