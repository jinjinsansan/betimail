"""afi.irah.uk の admin ページ構造を探索する。"""
import json
import os
from collections import Counter
from playwright.sync_api import sync_playwright

EMAIL = "admin@gmail.com"
PASSWORD = "1H22uFX5Nm0ZLlGiihZi"


def main():
    api_endpoints: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        def on_response(res):
            url = res.url
            if "irah.uk" in url and url not in api_endpoints:
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

        # ── ログインページ確認 ──
        print("[1] open login page...")
        page.goto("https://afi.irah.uk/auth/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        # フォーム要素を確認
        inputs = page.eval_on_selector_all(
            "input",
            "els => els.map(e => ({name:e.name, id:e.id, type:e.type, classes:e.className}))",
        )
        print(f"    inputs: {inputs}")
        buttons = page.eval_on_selector_all(
            "button",
            "els => els.map(e => ({text:e.textContent.trim(), type:e.type}))",
        )
        print(f"    buttons: {buttons}")

        # ── ログイン試行 ──
        print("\n[2] attempt login...")
        # luckymustard と同じパターン (#username, #password) を試す
        try:
            page.locator('input#username, input[type="email"], input[name*="email"]').first.fill(EMAIL)
            page.locator('input#password, input[type="password"]').first.fill(PASSWORD)
            # ログインボタン
            page.locator('button[type="submit"]').first.click()
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception as e:
            print(f"    login error: {e}")
            page.screenshot(path="exports/_afi_login.png", full_page=True)
            browser.close()
            return

        print(f"    after login URL: {page.url}")
        page.screenshot(path="exports/_afi_after_login.png", full_page=True)

        # ── ナビゲーション ──
        print("\n[3] nav links:")
        nav_links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href:e.href, text:e.textContent.trim().slice(0,60)}))",
        )
        seen = set()
        admin_links = []
        for l in nav_links:
            if "irah.uk" in l["href"] and l["href"] not in seen:
                seen.add(l["href"])
                if "/admin" in l["href"] or "/dashboard" in l["href"] or "/user" in l["href"] or "/member" in l["href"] or "/holder" in l["href"] or "/list" in l["href"]:
                    admin_links.append(l)
                    print(f"    [admin candidate] {l['text']:<30} → {l['href']}")

        # 全リンクをログ
        print(f"\n    全リンク {len(seen)} 件 (admin候補 {len(admin_links)} 件):")
        for l in nav_links[:30]:
            if "irah.uk" in l["href"]:
                print(f"      {l['text'][:40]:<40} → {l['href']}")

        # ── 候補ページを訪問 ──
        print("\n[4] visit admin candidate pages...")
        for l in admin_links:
            try:
                page.goto(l["href"], wait_until="networkidle", timeout=20000)
                print(f"    OK: {l['href']}")
            except Exception as e:
                print(f"    FAIL: {l['href']} → {e}")

        # ── 全 API endpoint 結果 ──
        print(f"\n[5] {len(api_endpoints)} JSON API endpoints captured:")
        for url, info in sorted(api_endpoints.items()):
            print(f"\n  {url}")
            print(f"    status={info['status']}, top-keys={info['keys']}")
            print(f"    preview: {info['body_preview']}")

        browser.close()


if __name__ == "__main__":
    main()
