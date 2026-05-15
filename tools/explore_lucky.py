"""luckymustard.uk の admin ページを探索し、ナビ・APIエンドポイントを列挙する。"""
import json
import os
import sys
from playwright.sync_api import sync_playwright

EMAIL = "admin@gmail.com"
PASSWORD = "gyGwngF43N3W9jEC92QE"


def main():
    api_endpoints: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        # API レスポンスを記録
        def on_response(res):
            url = res.url
            if "luckymustard.uk" in url and url not in api_endpoints:
                ct = (res.headers.get("content-type") or "").lower()
                if "application/json" in ct:
                    try:
                        body = res.json()
                        sample_keys = []
                        if isinstance(body, dict):
                            sample_keys = list(body.keys())[:8]
                        api_endpoints[url] = {
                            "status": res.status,
                            "keys": sample_keys,
                            "body_preview": json.dumps(body, ensure_ascii=False)[:400],
                        }
                    except Exception:
                        pass

        page.on("response", on_response)

        # ログイン
        print("[1] login...")
        page.goto("https://luckymustard.uk/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector('input#username', timeout=15000)
        page.locator('input#username').fill(EMAIL)
        page.locator('input#password').fill(PASSWORD)
        page.locator('button[type="submit"]:has-text("ログイン")').click()
        page.wait_for_url("**/admin/**", timeout=20000)
        page.wait_for_load_state("networkidle", timeout=15000)
        print(f"    URL: {page.url}")

        # ── ナビゲーション要素を列挙 ───────────
        print("\n[2] navigation links in admin sidebar/menu:")
        nav_links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, text: e.textContent.trim().slice(0, 50)}))",
        )
        admin_links = [l for l in nav_links if "luckymustard.uk" in l["href"] and "/admin/" in l["href"]]
        seen_hrefs = set()
        for l in admin_links:
            if l["href"] not in seen_hrefs:
                seen_hrefs.add(l["href"])
                print(f"    {l['text']:<30} → {l['href']}")

        # ── 各 admin リンクを訪問して API を観察 ──
        print("\n[3] visiting each admin page to discover APIs...")
        for href in sorted(seen_hrefs):
            try:
                page.goto(href, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_load_state("networkidle", timeout=10000)
                print(f"    visited: {href}")
            except Exception as e:
                print(f"    failed: {href} → {e}")

        # /admin/list-user に戻って1行クリック挙動
        print("\n[4] inspecting a row in /admin/list-user (click first row?)...")
        try:
            page.goto("https://luckymustard.uk/admin/list-user", wait_until="networkidle", timeout=20000)
            # 詳細リンクっぽいものを探す
            detail_links = page.eval_on_selector_all(
                'tr a, button[onclick]',
                "els => els.slice(0,5).map(e => ({text: e.textContent.trim().slice(0,30), href: e.href || '', onclick: e.getAttribute('onclick')||''}))"
            )
            print(f"    detail-link candidates in user table: {detail_links}")
        except Exception as e:
            print(f"    error: {e}")

        # 結果まとめ
        print("\n" + "=" * 60)
        print(f"[5] all distinct JSON API endpoints captured: {len(api_endpoints)}")
        for url, info in sorted(api_endpoints.items()):
            print(f"\n  {url}")
            print(f"    status: {info['status']}")
            print(f"    keys: {info['keys']}")
            print(f"    preview: {info['body_preview']}")

        browser.close()


if __name__ == "__main__":
    main()
