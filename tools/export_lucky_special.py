"""取引履歴からラッキーマスタード(3007)・スペシャルマスタード(3008)購入者を抽出し、
ユーザーリストとJOINしてメールアドレス付きで出力する。"""
import csv
import json
import os
from collections import defaultdict


def main():
    # ユーザーリスト読み込み (id, name, email, ...)
    with open("exports/lucky_NFT_holders.csv", encoding="utf-8") as f:
        users = {int(r["id"]): r for r in csv.DictReader(f)}
    print(f"ユーザーリスト読み込み: {len(users)} 名")

    # トランザクション
    with open("exports/_lucky_transactions_raw.json", encoding="utf-8") as f:
        txns = json.load(f)
    print(f"トランザクション総数: {len(txns)}")

    def aggregate(type_code: int, label: str, out_path: str):
        # from_id 別に集約
        per_user: dict = defaultdict(lambda: {
            "purchase_count": 0,
            "total_amount": 0,
            "first_purchase": None,
            "last_purchase": None,
            "packet_buys": [],
        })
        for t in txns:
            if t.get("type") != type_code:
                continue
            uid = t.get("from_id")
            if uid is None:
                continue
            agg = per_user[uid]
            agg["purchase_count"] += 1
            agg["total_amount"] += t.get("amount", 0) or 0
            ttime = t.get("transaction_time") or t.get("created_at", "")[:10]
            if not agg["first_purchase"] or ttime < agg["first_purchase"]:
                agg["first_purchase"] = ttime
            if not agg["last_purchase"] or ttime > agg["last_purchase"]:
                agg["last_purchase"] = ttime
            if t.get("packet_buy"):
                agg["packet_buys"].append(t.get("packet_buy"))

        rows = []
        for uid, agg in per_user.items():
            u = users.get(uid, {})
            rows.append({
                "user_id": uid,
                "name": u.get("name") or agg.get("name", ""),
                "email": (u.get("email") or "").strip().lower(),
                "purchase_count": agg["purchase_count"],
                "total_amount": agg["total_amount"],
                "first_purchase": agg["first_purchase"] or "",
                "last_purchase": agg["last_purchase"] or "",
                "packet_buy_ids": "|".join(str(p) for p in agg["packet_buys"]),
                "balance": u.get("balance", ""),
                "wallet_address": u.get("wallet_address") or "",
            })
        rows.sort(key=lambda r: r["first_purchase"])

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

        missing = sum(1 for r in rows if not r["email"])
        print(f"\n=== {label} ({len(rows)} 名) ===")
        print(f"  email 紐付け成功: {len(rows) - missing}")
        print(f"  email 紐付け失敗: {missing}")
        print(f"  → {out_path}")
        # サンプル
        for r in rows[:3]:
            print(f"    {r['name'][:12]:<12} {r['email']:<35} purchase_count={r['purchase_count']} total={r['total_amount']}")
        return rows

    lucky_rows = aggregate(3007, "ラッキーマスタード購入者", "exports/ラッキーマスタードNFT_保有者リスト.csv")
    special_rows = aggregate(3008, "スペシャルマスタード購入者", "exports/スペシャルマスタードNFT_保有者リスト.csv")

    # 統計
    lucky_emails = {r["email"] for r in lucky_rows if r["email"]}
    special_emails = {r["email"] for r in special_rows if r["email"]}
    print(f"\n=== 重複分析 ===")
    print(f"  ラッキーのみ: {len(lucky_emails - special_emails)}")
    print(f"  スペシャルのみ: {len(special_emails - lucky_emails)}")
    print(f"  両方: {len(lucky_emails & special_emails)}")


if __name__ == "__main__":
    main()
