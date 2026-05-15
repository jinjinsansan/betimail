"""nftportal.site から user list と withdraw-history を全件取得する。

エンドポイント:
- POST /admin/user-management/get-data?page=N
- POST /admin/withdraw-history/get-data?page=N  body: {keyword,month,year}

出力:
- exports/nftportal_users.json
- exports/nftportal_users.csv
- exports/nftportal_withdraws.json  (2025-11 ~ 当月までの全件)
- exports/nftportal_withdraws.csv
"""
import argparse
import csv
import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

EMAIL = "admin@gmail.com"
PASSWORD = "ArT73HBzxdsfAX"


def login(page):
    page.goto("https://nftportal.site/auth/login", wait_until="networkidle", timeout=30000)
    page.locator('input#username').fill(EMAIL)
    page.locator('input#password').fill(PASSWORD)
    page.locator('button[type="submit"]').first.click()
    page.wait_for_timeout(2500)


def fetch_paged(page, url: str, post_body: dict | None = None, label: str = "") -> list:
    """Laravel ペジネータ API を全件取得 (POST)。"""
    all_items = []
    page_num = 1
    while True:
        u = f"{url}{'&' if '?' in url else '?'}page={page_num}"
        body = page.evaluate(
            """async ({u, body}) => {
                const csrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/)||[])[1]||'');
                const r = await fetch(u, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json, text/plain, */*',
                        'X-XSRF-TOKEN': csrf,
                        'X-Requested-With': 'XMLHttpRequest',
                        'Content-Type': 'application/json',
                    },
                    body: body ? JSON.stringify(body) : null,
                });
                return { status: r.status, body: await r.json().catch(()=>null) };
            }""",
            {"u": u, "body": post_body},
        )
        if body.get("status") != 200 or not body.get("body"):
            print(f"    [{label}] page={page_num}: HTTP {body.get('status')}")
            break
        d = body["body"].get("data", {})
        items = d.get("data", []) if isinstance(d, dict) else []
        last_page = d.get("last_page", page_num) if isinstance(d, dict) else page_num
        total = d.get("total", "?") if isinstance(d, dict) else "?"
        all_items.extend(items)
        if page_num == 1:
            print(f"    [{label}] total={total}, last_page={last_page}, per_page={d.get('per_page')}")
        if page_num >= last_page or not items:
            break
        page_num += 1
    return all_items


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="exports")
    p.add_argument("--start-year", type=int, default=2025)
    p.add_argument("--start-month", type=int, default=11)
    args = p.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        print("[1] login")
        login(page)

        # ── ユーザーマスタ ──
        print("\n[2] fetch user list")
        page.goto("https://nftportal.site/admin/user-management", wait_until="networkidle", timeout=20000)
        users = fetch_paged(page,
            "https://nftportal.site/admin/user-management/get-data",
            None, "users")
        print(f"    users: {len(users)}")
        with open(f"{args.out_dir}/nftportal_users.json", "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        # CSV
        if users:
            keys = sorted({k for u in users for k in u.keys()})
            with open(f"{args.out_dir}/nftportal_users.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                w.writeheader()
                for u in users:
                    w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in u.items()})
            print(f"    → {args.out_dir}/nftportal_users.csv ({len(users)})")

        # ── 出金申請: 月ごとに取得 ──
        print("\n[3] fetch withdraw-history (月ごと)")
        page.goto("https://nftportal.site/admin/withdraw-history", wait_until="networkidle", timeout=20000)

        all_withdraws = []
        now = datetime.now()
        cur_year, cur_month = args.start_year, args.start_month
        while (cur_year, cur_month) <= (now.year, now.month):
            label = f"{cur_year}-{cur_month:02d}"
            items = fetch_paged(page,
                "https://nftportal.site/admin/withdraw-history/get-data",
                {"keyword": "", "month": cur_month, "year": cur_year},
                f"withdraw {label}")
            for it in items:
                it["_query_month"] = label
            print(f"    [withdraw {label}] {len(items)} 件")
            all_withdraws.extend(items)
            # next month
            if cur_month == 12:
                cur_month = 1; cur_year += 1
            else:
                cur_month += 1

        print(f"\n=== 合計 withdraw: {len(all_withdraws)} 件 ===")
        with open(f"{args.out_dir}/nftportal_withdraws.json", "w", encoding="utf-8") as f:
            json.dump(all_withdraws, f, ensure_ascii=False, indent=2)
        if all_withdraws:
            keys = sorted({k for w in all_withdraws for k in w.keys()})
            with open(f"{args.out_dir}/nftportal_withdraws.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                w.writeheader()
                for r in all_withdraws:
                    w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in r.items()})
            print(f"    → {args.out_dir}/nftportal_withdraws.csv")
            # サンプル
            print(f"\n  sample (first):")
            print(f"  keys: {sorted(all_withdraws[0].keys())}")
            print(f"  {json.dumps(all_withdraws[0], ensure_ascii=False)[:600]}")

        browser.close()


if __name__ == "__main__":
    main()
