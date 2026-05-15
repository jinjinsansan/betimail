"""afi.irah.uk (betibackoffice) から会員権NFTとパチスロホイホイの保有者を取得。

エンドポイント:
- /get-list-user → ユーザーマスタ
- /admin/nft/get-nft-purchase-history → 会員権NFT購入履歴
- /admin/device/get-device-purchase-history → パチスロホイホイ購入履歴
"""
import argparse
import csv
import json
import os
from playwright.sync_api import sync_playwright


EMAIL = "admin@gmail.com"
PASSWORD = "1H22uFX5Nm0ZLlGiihZi"


def login(page):
    page.goto("https://afi.irah.uk/auth/login", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('input#username, input[type="email"]', timeout=15000)
    page.locator('input#username, input[type="email"]').first.fill(EMAIL)
    page.locator('input#password, input[type="password"]').first.fill(PASSWORD)
    page.locator('button[type="submit"]').first.click()
    page.wait_for_url("**/admin/**", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)


def fetch_all_pages(page, base_url: str, label: str, method: str = "POST") -> list:
    """Laravel ペジネーター API を全件取得。"""
    all_items = []
    page_num = 1
    while True:
        url = f"{base_url}{'&' if '?' in base_url else '?'}page={page_num}"
        body = page.evaluate(
            """async ({u, method}) => {
                const csrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/)||[])[1]||'');
                const r = await fetch(u, {
                    method,
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json, text/plain, */*',
                        'X-XSRF-TOKEN': csrf,
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                });
                return { status: r.status, body: await r.json().catch(()=>null) };
            }""", {"u": url, "method": method},
        )
        if body.get("status") != 200 or not body.get("body"):
            print(f"    [{label}] page {page_num}: HTTP {body.get('status')}")
            break
        data = body["body"].get("data", {})
        items = data.get("data", []) if isinstance(data, dict) else []
        last_page = data.get("last_page", page_num) if isinstance(data, dict) else page_num
        total = data.get("total", "?") if isinstance(data, dict) else "?"
        all_items.extend(items)
        if page_num == 1:
            print(f"    [{label}] last_page={last_page}, total={total}, per_page={data.get('per_page') if isinstance(data, dict) else '?'}")
        if page_num >= last_page or not items:
            break
        page_num += 1
    print(f"    [{label}] retrieved {len(all_items)} items")
    return all_items


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="exports")
    p.add_argument("--headed", action="store_true")
    args = p.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        print("[1] login...")
        login(page)
        print(f"    OK, URL: {page.url}")

        # ── ユーザーマスタ ────────────────────
        print("\n[2] fetch user master (/get-list-user)...")
        page.goto("https://afi.irah.uk/admin/list-user", wait_until="networkidle", timeout=20000)
        users = fetch_all_pages(page, "https://afi.irah.uk/get-list-user?keyword=", "users")
        with open(f"{args.out_dir}/_afi_users_raw.json", "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        print(f"    → _afi_users_raw.json ({len(users)})")

        # 会員権NFT購入履歴
        print("\n[3] fetch 会員権NFT purchase history...")
        page.goto("https://afi.irah.uk/admin/nft", wait_until="networkidle", timeout=20000)
        nft_buys = fetch_all_pages(page, "https://afi.irah.uk/admin/nft/get-nft-purchase-history?", "nft")
        with open(f"{args.out_dir}/_afi_nft_raw.json", "w", encoding="utf-8") as f:
            json.dump(nft_buys, f, ensure_ascii=False, indent=2)

        # パチスロホイホイ購入履歴
        print("\n[4] fetch パチスロホイホイ purchase history...")
        page.goto("https://afi.irah.uk/admin/device", wait_until="networkidle", timeout=20000)
        device_buys = fetch_all_pages(page, "https://afi.irah.uk/admin/device/get-device-purchase-history?", "device")
        with open(f"{args.out_dir}/_afi_device_raw.json", "w", encoding="utf-8") as f:
            json.dump(device_buys, f, ensure_ascii=False, indent=2)

        browser.close()

        # ── サンプル表示 ──
        if nft_buys:
            print("\n=== 会員権NFT 購入 サンプル ===")
            print(f"    keys: {sorted(nft_buys[0].keys())}")
            print(f"    sample: {json.dumps(nft_buys[0], ensure_ascii=False)[:400]}")
        if device_buys:
            print("\n=== パチスロホイホイ 購入 サンプル ===")
            print(f"    keys: {sorted(device_buys[0].keys())}")
            print(f"    sample: {json.dumps(device_buys[0], ensure_ascii=False)[:400]}")

        # ── ユーザーマスタと突合 ──
        users_by_id = {int(u["id"]): u for u in users if u.get("id") is not None}

        def aggregate(records, label, slug):
            """user_id ベースで集計し、emailと結合してCSV出力。"""
            from collections import defaultdict
            agg: dict = defaultdict(lambda: {"count": 0, "packets": 0, "buy_dates": [], "samples": []})
            for r in records:
                uid = r.get("user_id")
                if uid is None:
                    continue
                a = agg[int(uid)]
                a["count"] += 1
                a["packets"] += (r.get("packet") or 0)
                a["buy_dates"].append(r.get("buy_date") or r.get("created_at") or "")
                a["samples"].append(r.get("id"))
            rows = []
            for uid, a in agg.items():
                u = users_by_id.get(uid, {})
                rows.append({
                    "user_id": uid,
                    "name": u.get("name", ""),
                    "email": (u.get("email") or "").strip().lower(),
                    "purchase_count": a["count"],
                    "total_packets": a["packets"],
                    "first_buy": min((d for d in a["buy_dates"] if d), default=""),
                    "last_buy": max((d for d in a["buy_dates"] if d), default=""),
                })
            rows.sort(key=lambda r: r["first_buy"])
            out_path = f"{args.out_dir}/afi_{slug}_holders.csv"
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
            missing = sum(1 for r in rows if not r["email"])
            print(f"\n{label}: {len(rows)} 名 (email紐付け失敗 {missing} 名)")
            print(f"  → {out_path}")
            return rows

        nft_rows = aggregate(nft_buys, "会員権NFT", "kaiin") if nft_buys else []
        device_rows = aggregate(device_buys, "パチスロホイホイ", "pachi") if device_buys else []


if __name__ == "__main__":
    main()
