"""afi.irah.uk スクレイピング結果のうち、DB未登録の会員権NFT実購入者を取り込む。

0円会員(hardcode)は除外。差分 62 名を追加。
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--nft-json", required=True, help="exports/_afi_nft_raw.json")
    p.add_argument("--users-json", required=True, help="exports/_afi_users_raw.json")
    p.add_argument("--diff-csv", required=True, help="afi-only emails (会員権)")
    p.add_argument("--source-file", default="afi_kaiin_diff", help="DB の source_file 識別子")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--replace", action="store_true")
    p.add_argument("--regen-members", action="store_true")
    p.add_argument("--members-csv", default=os.path.join(ROOT, "data", "members.csv"))
    args = p.parse_args()

    with open(args.users_json, encoding="utf-8") as f:
        users = {int(u["id"]): u for u in json.load(f)}
    with open(args.nft_json, encoding="utf-8") as f:
        nft = json.load(f)
    with open(args.diff_csv, encoding="utf-8") as f:
        diff_emails = {r["email"].strip().lower() for r in csv.DictReader(f)}

    print(f"users: {len(users)}, nft tx: {len(nft)}, diff emails: {len(diff_emails)}")

    # hardcode 除外
    records = []
    skipped_hardcode = 0
    for r in nft:
        tx_id = r.get("transaction_id") or ""
        if "hardcode" in tx_id:
            skipped_hardcode += 1
            continue
        uid = r.get("user_id")
        u = users.get(uid, {})
        email = (u.get("email") or "").strip().lower()
        if not email or email not in diff_emails:
            continue
        records.append({
            "email": email,
            "name": u.get("name") or "",
            "nft_type": "会員権NFT",
            "amount_jpy": int(r.get("amount") or 0) if r.get("amount") else None,
            "units": int(r.get("packet") or 0) if r.get("packet") else None,
            "team": "",
            "transaction_id": tx_id,
            "purchased_at": (r.get("buy_date") or r.get("created_at") or "")[:10],
            "status": "purchased",
            "returns_usdt": None,
            "notes": f"afi_user_id={uid} / tx_id={tx_id} / packet={r.get('packet')} / source=afi",
            "source_file": args.source_file,
        })

    print(f"取込対象: {len(records)} 件 (ユニーク email {len(set(r['email'] for r in records))} 名)")
    print(f"hardcode スキップ: {skipped_hardcode} 件")

    if args.dry_run:
        print("🟡 dry-run")
        return

    import db
    db.init_db()
    if args.replace:
        d = db.clear_purchases(source_file=args.source_file)
        print(f"既存 source_file={args.source_file} 削除: {d}")
    inserted = db.bulk_insert_purchases(records)
    print(f"✅ {inserted} 件挿入")
    print(f"全 purchases: {db.count_purchases()} / ユニーク email: {db.distinct_emails_in_purchases()}")

    if args.regen_members:
        from tools.import_purchases import regenerate_members_csv
        conn = db.get_conn()
        all_p = [dict(r) for r in conn.execute("SELECT * FROM purchases").fetchall()]
        res = regenerate_members_csv(all_p, args.members_csv)
        print(f"✅ members.csv: {res['members_written']} 名 → {res['path']}")


if __name__ == "__main__":
    main()
