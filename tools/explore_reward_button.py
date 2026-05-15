"""/admin/lucky-mustard の「報酬分配」ボタンとモーダルを調査する。"""
import json
import os
from playwright.sync_api import sync_playwright

EMAIL = "admin@gmail.com"
PASSWORD = "gyGwngF43N3W9jEC92QE"


def main():
    os.makedirs("exports", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        # ログイン
        print("[1] login")
        page.goto("https://luckymustard.uk/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector('input#username', timeout=15000)
        page.locator('input#username').fill(EMAIL)
        page.locator('input#password').fill(PASSWORD)
        page.locator('button[type="submit"]').click()
        page.wait_for_url("**/admin/**", timeout=20000)

        # lucky-mustard ページへ
        print("[2] goto /admin/lucky-mustard")
        page.goto("https://luckymustard.uk/admin/lucky-mustard", wait_until="networkidle", timeout=30000)
        page.screenshot(path="exports/_reward_01_page.png", full_page=True)

        # ボタンを列挙
        print("\n[3] all buttons on page:")
        buttons = page.eval_on_selector_all(
            "button, a.btn, input[type='button'], input[type='submit']",
            "els => els.map(e => ({text: e.textContent.trim().slice(0,30), classes: e.className, id: e.id, type: e.type || '', tag: e.tagName}))",
        )
        for i, b in enumerate(buttons):
            print(f"  [{i}] {b}")

        # 「報酬」「分配」「reward」を含むものを抽出
        print("\n[4] candidate buttons (containing 報酬/分配/reward):")
        candidates = []
        for b in buttons:
            t = b["text"]
            c = b.get("classes", "")
            if any(k in t for k in ["報酬", "分配", "reward", "Reward"]) or "yellow" in c.lower() or "warning" in c.lower() or "btn-bg-eec967" in c:
                candidates.append(b)
                print(f"  → {b}")

        # 報酬分配ボタンをクリックしてモーダル表示
        print("\n[5] try clicking 報酬分配 button...")
        try:
            btn = page.locator('button:has-text("報酬分配"), a:has-text("報酬分配"), button:has-text("reward"), button:has-text("分配")').first
            btn.wait_for(state="visible", timeout=5000)
            print(f"    found: text={btn.text_content()}")
            btn.click()
            page.wait_for_timeout(1500)
            page.screenshot(path="exports/_reward_02_modal.png", full_page=True)

            # モーダル内の input/button を列挙
            print("\n[6] inputs in modal:")
            inputs = page.eval_on_selector_all(
                "input, textarea",
                """els => els.filter(e => e.offsetParent !== null).map(e => ({
                    name: e.name, id: e.id, type: e.type, placeholder: e.placeholder,
                    value: e.value, classes: e.className,
                    parent_classes: e.parentElement?.className||''
                }))"""
            )
            for i, inp in enumerate(inputs):
                print(f"  [{i}] {inp}")

            print("\n[7] visible buttons in modal area:")
            modal_buttons = page.eval_on_selector_all(
                ".modal button, [role='dialog'] button, .v-dialog button, button",
                """els => els.filter(e => e.offsetParent !== null).map(e => ({
                    text: e.textContent.trim().slice(0,40),
                    classes: e.className, id: e.id
                }))"""
            )
            # 重複除去
            seen = set()
            for b in modal_buttons:
                key = (b["text"], b["classes"])
                if key in seen:
                    continue
                seen.add(key)
                print(f"  {b}")

            # モーダル全体のHTMLを保存
            with open("exports/_reward_modal.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print("\n[8] full page HTML saved → exports/_reward_modal.html")
        except Exception as e:
            print(f"    click failed: {e}")

        browser.close()


if __name__ == "__main__":
    main()
