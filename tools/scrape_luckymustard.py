"""luckymustard.uk の管理者ページから保有者一覧をスクレイピング。

API は Laravel ペジネータ形式:
  GET https://luckymustard.uk/get-list-user?page=N&keyword=
  → { success, data: { current_page, data: [...], last_page, per_page, ... } }

ログインで取得した cookie を維持したまま page=1..last_page を順次取得。
"""
import argparse
import csv
import json
import os
import sys

from playwright.sync_api import sync_playwright


def run(email: str, password: str, output: str, headed: bool = False):
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        # ── 1. ログイン ──────────────────────────
        print("[1] login...")
        page.goto("https://luckymustard.uk/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector('input#username', timeout=15000)
        page.locator('input#username').fill(email)
        page.locator('input#password').fill(password)
        page.locator('button[type="submit"]:has-text("ログイン")').click()
        page.wait_for_url("**/admin/**", timeout=20000)
        page.wait_for_load_state("networkidle", timeout=15000)
        print(f"    logged in, current URL: {page.url}")

        # ── 2a. ページが自分で叩いている req メソッドを確認 ──
        print("[2a] inspecting initial request method...")
        captured_method = None
        captured_headers = None
        def on_req(req):
            nonlocal captured_method, captured_headers
            if "get-list-user" in req.url and captured_method is None:
                captured_method = req.method
                captured_headers = req.headers
                print(f"    method={req.method} headers={dict(req.headers)}")
        page.on("request", on_req)
        # 再描画させて requestを観察
        page.goto("https://luckymustard.uk/admin/list-user", wait_until="networkidle", timeout=20000)
        print(f"    captured method: {captured_method}")
        method_to_use = captured_method or "GET"

        # ── 2. API を直接叩いて全ページ取得 ───────
        print("[2] fetching pages...")
        all_items: list[dict] = []
        page_num = 1
        last_page = None
        per_page_total = None

        while True:
            # ブラウザの fetch で叩く。Laravel の CSRF (XSRF-TOKEN cookie) を X-XSRF-TOKEN ヘッダに付与
            body = page.evaluate(
                """async ({url, method}) => {
                    const csrfCookie = document.cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('XSRF-TOKEN='));
                    const csrf = csrfCookie ? decodeURIComponent(csrfCookie.split('=')[1]) : '';
                    const opts = {
                        method,
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-XSRF-TOKEN': csrf,
                        },
                        credentials: 'include',
                    };
                    const r = await fetch(url, opts);
                    return { status: r.status, body: await r.json().catch(() => null) };
                }""",
                {
                    "url": f"https://luckymustard.uk/get-list-user?page={page_num}&keyword=",
                    "method": method_to_use,
                },
            )
            if body.get("status") != 200 or not body.get("body"):
                print(f"    ❌ page={page_num} HTTP {body.get('status')} (method={method_to_use})")
                break
            body = body["body"]
            data = body.get("data", {})
            items = data.get("data", [])
            last_page = data.get("last_page", page_num)
            per_page = data.get("per_page", len(items))
            total = data.get("total", "?")
            if per_page_total is None:
                per_page_total = per_page
                print(f"    per_page={per_page}, last_page={last_page}, total={total}")
            print(f"    page {page_num}/{last_page}: {len(items)} items (cumulative {len(all_items) + len(items)})")
            all_items.extend(items)
            if page_num >= last_page or not items:
                break
            page_num += 1

        browser.close()

        if not all_items:
            print("❌ no items fetched")
            return

        # ── 3. CSV出力 ──────────────────────────
        print(f"[3] writing CSV: {output}")
        # 共通する全フィールドを抽出
        fieldnames = []
        seen = set()
        for d in all_items:
            for k in d.keys():
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)
        with open(output, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in all_items:
                # ネスト値は JSON 文字列に変換
                flat = {}
                for k in fieldnames:
                    v = row.get(k)
                    if isinstance(v, (dict, list)):
                        flat[k] = json.dumps(v, ensure_ascii=False)
                    else:
                        flat[k] = v if v is not None else ""
                w.writerow(flat)
        print(f"✅ {len(all_items)} 行を {output} に出力")
        print(f"   列: {fieldnames}")

        # サンプル表示
        if all_items:
            print()
            print("=== 先頭 1 件 ===")
            print(json.dumps(all_items[0], ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--headed", action="store_true")
    args = p.parse_args()
    run(args.email, args.password, args.output, args.headed)


if __name__ == "__main__":
    main()
