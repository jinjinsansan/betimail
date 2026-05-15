"""nftportal.site の admin ページ構造を探索。"""
import json
import os
from playwright.sync_api import sync_playwright

EMAIL = os.getenv("NFTPORTAL_ADMIN_EMAIL", "admin@gmail.com")
PASSWORD = os.getenv("NFTPORTAL_ADMIN_PASSWORD", "")


def main():
    if not PASSWORD:
        raise RuntimeError("NFTPORTAL_ADMIN_PASSWORD が未設定です")
    api_endpoints: dict[str, dict] = {}
    os.makedirs("exports", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        def on_response(res):
            url = res.url
            if "nftportal" in url and url not in api_endpoints:
                ct = (res.headers.get("content-type") or "").lower()
                if "application/json" in ct:
                    try:
                        body = res.json()
                        api_endpoints[url] = {
                            "status": res.status,
                            "keys": list(body.keys())[:10] if isinstance(body, dict) else None,
                            "body_preview": json.dumps(body, ensure_ascii=False)[:400],
                        }
                    except Exception:
                        pass
        page.on("response", on_response)

        print("[1] visit login page")
        page.goto("https://nftportal.site/auth/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        # フォーム要素を調査
        inputs = page.eval_on_selector_all(
            "input",
            "els => els.map(e => ({name:e.name, id:e.id, type:e.type}))",
        )
        print(f"    login inputs: {inputs}")

        print("\n[2] login")
        page.locator('input#username').fill(EMAIL)
        page.locator('input#password').fill(PASSWORD)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_timeout(3000)
        page.goto("https://nftportal.site/admin/user-management", wait_until="networkidle", timeout=20000)
        print(f"    after admin page: {page.url}")

        # 既に判明: /admin/user-management で /admin/user-management/get-data がある
        # 他の admin ページを試す
        candidates = [
            "https://nftportal.site/admin/user-management",
            "https://nftportal.site/admin/withdraw",
            "https://nftportal.site/admin/withdraw-requests",
            "https://nftportal.site/admin/withdraw-request",
            "https://nftportal.site/admin/withdraw-management",
            "https://nftportal.site/admin/payout",
            "https://nftportal.site/admin/payout-management",
            "https://nftportal.site/admin/transactions",
            "https://nftportal.site/admin/transaction-history",
            "https://nftportal.site/admin/nft",
            "https://nftportal.site/admin/buyback",
            "https://nftportal.site/admin/buyback-management",
            "https://nftportal.site/admin/list-user",
            "https://nftportal.site/admin",
            "https://nftportal.site/admin/dashboard",
        ]
        print("\n[3] try admin URLs:")
        for href in candidates:
            try:
                resp = page.goto(href, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_load_state("networkidle", timeout=8000)
                print(f"    {resp.status if resp else '?':<4} {href} -> {page.url}")
            except Exception as e:
                print(f"    ERR  {href}: {str(e)[:80]}")

        # サイドバー・ナビ
        print("\n[4] sidebar / nav探索 (admin page 内):")
        page.goto("https://nftportal.site/admin/user-management", wait_until="networkidle", timeout=15000)
        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href:e.href, text:e.textContent.trim().slice(0,60)}))",
        )
        for l in links:
            if "nftportal" in l.get("href",""):
                print(f"    {l['text'][:40]:<40} → {l['href']}")

        # 結果
        print(f"\n[5] API endpoints captured ({len(api_endpoints)}):")
        for url, info in sorted(api_endpoints.items()):
            print(f"\n  {url}")
            print(f"    status: {info['status']}, keys: {info['keys']}")
            print(f"    preview: {info['body_preview']}")

        browser.close()


if __name__ == "__main__":
    main()
