"""withdraw-history の月切替動作を観察し、リクエストパラメータを判明させる。"""
import json
import os
from playwright.sync_api import sync_playwright

EMAIL = os.getenv("NFTPORTAL_ADMIN_EMAIL", "admin@gmail.com")
PASSWORD = os.getenv("NFTPORTAL_ADMIN_PASSWORD", "")


def main():
    if not PASSWORD:
        raise RuntimeError("NFTPORTAL_ADMIN_PASSWORD が未設定です")
    os.makedirs("exports", exist_ok=True)
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        def on_request(req):
            if "nftportal" in req.url and "get-data" in req.url:
                captured.append({
                    "url": req.url,
                    "method": req.method,
                    "post_data": req.post_data,
                    "headers": dict(req.headers),
                })
        page.on("request", on_request)

        # ログイン
        page.goto("https://nftportal.site/auth/login", wait_until="networkidle", timeout=30000)
        page.locator('input#username').fill(EMAIL)
        page.locator('input#password').fill(PASSWORD)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_timeout(2500)

        # withdraw-history へ
        page.goto("https://nftportal.site/admin/withdraw-history", wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(1500)

        # 月選択 input を試す（datepicker などで前月変更）
        # pick_month に値をセットして変更イベントを発火
        for target_month in ["2025/11", "2025/12", "2026/01", "2026/02", "2026/03", "2026/04"]:
            page.evaluate(f"""
                const el = document.getElementById('pick_month');
                if (el) {{
                    el.value = '{target_month}';
                    el.dispatchEvent(new Event('change'));
                    el.dispatchEvent(new Event('input'));
                }}
            """)
            page.wait_for_timeout(2500)
            print(f"set month to {target_month}, requests so far: {len(captured)}")

        # 各リクエストの違いを表示
        print(f"\n=== captured {len(captured)} requests ===")
        for i, c in enumerate(captured[-10:]):
            print(f"\n  [{i}] {c['method']} {c['url']}")
            if c["post_data"]:
                print(f"      post_data: {c['post_data'][:300]}")

        browser.close()


if __name__ == "__main__":
    main()
