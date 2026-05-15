"""ログインページの DOM を取得し、input 要素の属性をすべて吐く。"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://luckymustard.uk/", wait_until="networkidle", timeout=30000)
    inputs = page.eval_on_selector_all(
        "input",
        """els => els.map(e => ({
            name: e.name, id: e.id, type: e.type,
            placeholder: e.placeholder,
            classes: e.className,
            label: e.closest('label')?.textContent?.trim() || ''
        }))""",
    )
    for i, inp in enumerate(inputs):
        print(f"  [{i}] {inp}")
    print()
    print("=== buttons ===")
    buttons = page.eval_on_selector_all(
        "button",
        "els => els.map(e => ({text: e.textContent.trim(), type: e.type, classes: e.className}))",
    )
    for b in buttons:
        print(f"  {b}")
    browser.close()
