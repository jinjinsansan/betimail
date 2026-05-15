"""afi.irah.uk からスクレイピングしたリストを VPS DB と突合する。

VPS の DB から会員権/パチスロ保有者を取得し、afi の結果と比較して差分を出す。
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_csv_emails(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            email = (r.get("email") or "").strip().lower()
            if email:
                out[email] = r
    return out


def main():
    # afi スクレイピング結果
    afi_kaiin = load_csv_emails("exports/afi_kaiin_holders.csv")
    afi_pachi = load_csv_emails("exports/afi_pachi_holders.csv")
    print(f"afi 会員権: {len(afi_kaiin)} 名")
    print(f"afi パチスロ: {len(afi_pachi)} 名")

    # DB の会員権/パチスロ保有者
    import db
    conn = db.get_conn()
    db_kaiin = {row["email"] for row in conn.execute(
        "SELECT DISTINCT email FROM purchases WHERE nft_type='会員権NFT'"
    ).fetchall()}
    db_pachi = {row["email"] for row in conn.execute(
        "SELECT DISTINCT email FROM purchases WHERE nft_type='パチスロホイホイNFT'"
    ).fetchall()}
    print(f"DB 会員権: {len(db_kaiin)} 名")
    print(f"DB パチスロ: {len(db_pachi)} 名")

    def diff(label, afi_emails: set, db_emails: set, afi_dict: dict, slug: str):
        only_afi = afi_emails - db_emails
        only_db = db_emails - afi_emails
        both = afi_emails & db_emails

        print(f"\n=== {label} ===")
        print(f"  両方: {len(both)}")
        print(f"  afi のみ (DB未登録): {len(only_afi)}")
        print(f"  DB のみ (afi未取得): {len(only_db)}")

        # 差分 CSV 出力
        if only_afi:
            path = f"exports/diff_{slug}_only_afi.csv"
            rows = [afi_dict[e] for e in sorted(only_afi)]
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
            print(f"  → {path} ({len(rows)})")

        if only_db:
            path = f"exports/diff_{slug}_only_db.csv"
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("email\n")
                for e in sorted(only_db):
                    f.write(e + "\n")
            print(f"  → {path} ({len(only_db)})")
            # サンプル
            for e in sorted(only_db)[:10]:
                print(f"    DB-only: {e}")

    diff("会員権NFT", set(afi_kaiin), db_kaiin, afi_kaiin, "kaiin")
    diff("パチスロホイホイNFT", set(afi_pachi), db_pachi, afi_pachi, "pachi")


if __name__ == "__main__":
    main()
