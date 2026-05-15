"""取引履歴 JSON とユーザーリスト CSV から、ラッキー(type=3007) と スペシャル(type=3008)
の購入を purchases テーブルに取り込む。

入力:
    --transactions exports/_lucky_transactions_raw.json
    --users exports/lucky_NFT_holders.csv
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


TYPE_MAP = {
    3007: ("ラッキーマスタードNFT", "luckymustard_3007"),
    3008: ("スペシャルマスタードNFT", "luckymustard_3008"),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--transactions", required=True)
    p.add_argument("--users", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--replace", action="store_true",
                   help="既存の source_file=luckymustard.csv / lucky.csv / luckymustard_3007 / 3008 を全削除")
    p.add_argument("--regen-members", action="store_true")
    p.add_argument("--members-csv", default=os.path.join(ROOT, "data", "members.csv"))
    args = p.parse_args()

    # ユーザーリスト読み込み (id -> {name, email})
    with open(args.users, encoding="utf-8") as f:
        users = {int(r["id"]): r for r in csv.DictReader(f)}
    print(f"users loaded: {len(users)}")

    with open(args.transactions, encoding="utf-8") as f:
        txns = json.load(f)
    print(f"transactions loaded: {len(txns)}")

    # 取り込むレコードを構築
    records = []
    type_counts = {}
    for t in txns:
        type_code = t.get("type")
        if type_code not in TYPE_MAP:
            continue
        nft_type, source_file = TYPE_MAP[type_code]

        from_id = t.get("from_id")
        u = users.get(from_id, {})
        email = (u.get("email") or "").strip().lower()
        if not email:
            continue
        name = (u.get("name") or t.get("name") or "").strip()

        notes_data = {
            "lucky_user_id": from_id,
            "txn_id": t.get("id"),
            "transaction_time": t.get("transaction_time"),
            "packet_buy": t.get("packet_buy"),
            "amount_usdt": t.get("amount"),
            "type": type_code,
            "action": t.get("action"),
        }
        notes = " / ".join(f"{k}={v}" for k, v in notes_data.items() if v not in (None, "", 0))

        records.append({
            "email": email,
            "name": name,
            "nft_type": nft_type,
            "amount_jpy": None,
            "units": 1,                  # 1 transaction = 1 packet 購入
            "team": "",
            "transaction_id": f"luckymustard_tx_{t.get('id')}",
            "purchased_at": (t.get("transaction_time") or t.get("created_at") or "")[:10].replace(".", "-"),
            "status": "purchased",
            "returns_usdt": None,
            "notes": notes,
            "source_file": source_file,
        })
        type_counts[type_code] = type_counts.get(type_code, 0) + 1

    print(f"\n取り込み対象:")
    for tc, cnt in type_counts.items():
        nft = TYPE_MAP[tc][0]
        unique_users = len(set(r["email"] for r in records if r["nft_type"] == nft))
        print(f"  {nft} (type={tc}): {cnt} 行 / {unique_users} 名")

    if args.dry_run:
        print("\n🟡 dry-run: DB書き込みなし")
        return

    import db
    db.init_db()
    if args.replace:
        # 旧 lucky.csv ベース + 今回の 2 source を削除
        for sf in ("lucky.csv", "luckymustard_3007", "luckymustard_3008"):
            d = db.clear_purchases(source_file=sf)
            if d:
                print(f"🗑️  source_file={sf} の既存 {d} 件削除")
    inserted = db.bulk_insert_purchases(records)
    print(f"\n✅ {inserted} 件挿入")
    print(f"全 purchases: {db.count_purchases()} / ユニークemail: {db.distinct_emails_in_purchases()}")

    if args.regen_members:
        print("\n[regen members.csv]")
        from tools.import_purchases import regenerate_members_csv
        conn = db.get_conn()
        all_p = [dict(r) for r in conn.execute("SELECT * FROM purchases").fetchall()]
        res = regenerate_members_csv(all_p, args.members_csv)
        print(f"✅ {res['members_written']} 名 → {res['path']}")


if __name__ == "__main__":
    main()
