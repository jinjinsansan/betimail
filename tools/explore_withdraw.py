"""nftportal.site の出金申請ページのAPIを詳しく観察。"""
import json
import os
from playwright.sync_api import sync_playwright

EMAIL = os.getenv("NFTPORTAL_ADMIN_EMAIL", "admin@gmail.com")
PASSWORD = os.getenv("NFTPORTAL_ADMIN_PASSWORD", "")


def main():
    if not PASSWORD:
        raise RuntimeError("NFTPORTAL_ADMIN_PASSWORD が未設定です")
    api_endpoints = {}
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
                            "method": res.request.method,
                            "keys": list(body.keys())[:10] if isinstance(body, dict) else None,
                            "body_preview": json.dumps(body, ensure_ascii=False)[:600],
                        }
                    except Exception:
                        pass
        page.on("response", on_response)

        # ログイン
        page.goto("https://nftportal.site/auth/login", wait_until="networkidle", timeout=30000)
        page.locator('input#username').fill(EMAIL)
        page.locator('input#password').fill(PASSWORD)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_timeout(3000)

        # 各 admin ページを訪問して API キャプチャ
        for path in [
            "/admin/withdraw-history",
            "/admin/reward-history",
            "/admin/staking-history",
            "/admin/referral-reward",
        ]:
            url = f"https://nftportal.site{path}"
            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
                print(f"visited: {url}")
                # 月切替などUIを試す（前月など）
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"failed: {url}: {e}")

        print(f"\n=== {len(api_endpoints)} API endpoints captured ===")
        for url, info in sorted(api_endpoints.items()):
            print(f"\n  [{info['method']}] {url}")
            print(f"    status: {info['status']}, keys: {info['keys']}")
            print(f"    preview: {info['body_preview']}")

        # 出金申請ページのHTMLとスクショ
        page.goto("https://nftportal.site/admin/withdraw-history", wait_until="networkidle", timeout=20000)
        page.screenshot(path="exports/_nftportal_withdraw.png", full_page=True)
        # フィルタUIを観察
        inputs = page.eval_on_selector_all(
            "input,select",
            "els => els.map(e => ({type:e.type, name:e.name, id:e.id, placeholder:e.placeholder, value:e.value, options:e.tagName==='SELECT'?Array.from(e.options).map(o=>o.value):[]}))"
        )
        print("\n=== withdraw-history のフィルタ ===")
        for i, inp in enumerate(inputs):
            print(f"  [{i}] {inp}")

        browser.close()


if __name__ == "__main__":
    main()
