"""ログイン後の挙動を細かく観察。"""
import json
import os
from playwright.sync_api import sync_playwright

EMAIL = os.getenv("NFTPORTAL_ADMIN_EMAIL", "admin@gmail.com")
PASSWORD = os.getenv("NFTPORTAL_ADMIN_PASSWORD", "")


def main():
    if not PASSWORD:
        raise RuntimeError("NFTPORTAL_ADMIN_PASSWORD が未設定です")
    requests_seen = []
    responses_seen = []
    os.makedirs("exports", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        page.on("request", lambda req: requests_seen.append((req.method, req.url)) if "nftportal" in req.url else None)
        def on_resp(res):
            if "nftportal" in res.url:
                ct = (res.headers.get("content-type") or "").lower()
                try:
                    body = res.json() if "application/json" in ct else (res.text()[:500] if "text" in ct else None)
                except Exception:
                    body = None
                responses_seen.append((res.status, res.url, body))
        page.on("response", on_resp)

        page.goto("https://nftportal.site/auth/login", wait_until="networkidle", timeout=30000)

        # ボタンを観察
        buttons = page.eval_on_selector_all(
            "button",
            "els => els.map(e => ({text:e.textContent.trim(), type:e.type, classes:e.className}))",
        )
        print(f"buttons: {buttons}")

        # フィールドを埋める
        page.locator('input#username').fill(EMAIL)
        page.locator('input#password').fill(PASSWORD)
        # ログインクリック
        print("clicking login...")
        page.locator('button[type="submit"]').first.click()
        # 5秒待つ
        page.wait_for_timeout(5000)
        print(f"current URL: {page.url}")

        # 画面のテキスト（エラーメッセージ抽出）
        text_content = page.eval_on_selector_all(
            ".error, .alert, .text-danger, .invalid-feedback, [class*='error']",
            "els => els.map(e => e.textContent.trim()).filter(t => t)"
        )
        print(f"\nerror messages: {text_content}")

        # 入力後のスクリーンショット
        page.screenshot(path="exports/_nftportal_after_login.png", full_page=True)

        print(f"\n=== requests ===")
        for m, u in requests_seen[-20:]:
            print(f"  {m} {u}")
        print(f"\n=== responses (status / url / preview) ===")
        for s, u, b in responses_seen[-15:]:
            preview = json.dumps(b, ensure_ascii=False)[:200] if isinstance(b, (dict, list)) else (str(b)[:200] if b else "")
            print(f"  {s} {u}")
            if preview:
                print(f"    body: {preview}")

        browser.close()


if __name__ == "__main__":
    main()
