"""ラッキーマスタード保有者 CSV (scrape_luckymustard.py の出力) を取り込む。

balance>0 または packet>0 の実購入者のみを purchases テーブルに追加する。
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="lucky_NFT_holders.csv")
    p.add_argument("--nft-type", default="ラッキーマスタードNFT")
    p.add_argument("--source-file", default="lucky.csv", help="DB の source_file 識別子")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--replace", action="store_true", help="同じ source_file の既存レコードを削除してから挿入")
    p.add_argument("--regen-members", action="store_true",
                   help="既存データ + 新規をマージして members.csv を再生成")
    p.add_argument("--members-csv", default=os.path.join(ROOT, "data", "members.csv"))
    args = p.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ ファイルが見つかりません: {args.file}", file=sys.stderr)
        sys.exit(1)

    # 読み込み + フィルタ
    accepted = []
    skipped_no_balance = 0
    with open(args.file, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            email = (r.get("email") or "").strip().lower()
            if not email or "@" not in email:
                continue
            try:
                balance = float(r.get("balance") or 0)
            except ValueError:
                balance = 0
            try:
                packet = int(r.get("packet") or 0)
            except ValueError:
                packet = 0
            if balance <= 0 and packet <= 0:
                skipped_no_balance += 1
                continue
            accepted.append({"row": r, "balance": balance, "packet": packet})

    print(f"📥 読み込み: {args.file}")
    print(f"   有効 (balance>0 or packet>0): {len(accepted)} 件")
    print(f"   スキップ (balance=0 かつ packet=0): {skipped_no_balance} 件")

    # purchases レコードに変換
    records = []
    for entry in accepted:
        r = entry["row"]
        notes_data = {
            "lucky_user_id": r.get("id", ""),
            "balance": r.get("balance", ""),
            "packet": r.get("packet", ""),
            "title": r.get("title", ""),
            "leader_enable": r.get("leader_enable", ""),
            "wallet_address": r.get("wallet_address") or "",
            "status": r.get("status", ""),
        }
        notes = " / ".join(f"{k}={v}" for k, v in notes_data.items() if v != "")
        purchased_at = (r.get("created_at") or "")[:10]
        records.append({
            "email": (r.get("email") or "").strip().lower(),
            "name": (r.get("name") or "").strip(),
            "nft_type": args.nft_type,
            "amount_jpy": None,            # 不明（USDT払いのため）
            "units": None,                 # 意味不明なので入れない
            "team": "",                    # 不明
            "transaction_id": f"lucky_id_{r.get('id', '')}",
            "purchased_at": purchased_at,
            "status": r.get("status", ""),
            "returns_usdt": None,          # 意味不明なので入れない
            "notes": notes,
            "source_file": args.source_file,
        })

    if args.dry_run:
        print()
        print("🟡 dry-run: DB書き込みなし")
        print(f"=== 先頭 3 件 ===")
        for rec in records[:3]:
            print(json.dumps(rec, ensure_ascii=False, indent=2))
        return

    # DB 取り込み
    import db
    db.init_db()
    if args.replace:
        deleted = db.clear_purchases(source_file=args.source_file)
        print(f"🗑️  source_file={args.source_file} の既存 {deleted} 件を削除")
    inserted = db.bulk_insert_purchases(records)
    print(f"✅ {inserted} 件挿入完了")
    print(f"   全 purchases: {db.count_purchases()} / ユニーク email: {db.distinct_emails_in_purchases()}")

    # members.csv 再生成
    if args.regen_members:
        print()
        print("[regen members.csv] 全 purchases から集約中...")
        from tools.import_purchases import regenerate_members_csv
        conn = db.get_conn()
        all_purchases = [dict(r) for r in conn.execute("SELECT * FROM purchases").fetchall()]
        res = regenerate_members_csv(all_purchases, args.members_csv)
        print(f"✅ members.csv 再生成: {res['members_written']} 名 → {res['path']}")


if __name__ == "__main__":
    main()
