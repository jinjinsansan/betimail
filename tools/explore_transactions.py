"""取引履歴と special-mustard / lucky-mustard 専用ページの内容を詳しく調査する。"""
import json
import os
import sys
from collections import Counter
from playwright.sync_api import sync_playwright

EMAIL = os.getenv("LUCKY_ADMIN_EMAIL", "admin@gmail.com")
PASSWORD = os.getenv("LUCKY_ADMIN_PASSWORD", "")


def login(page):
    if not PASSWORD:
        raise RuntimeError("LUCKY_ADMIN_PASSWORD が未設定です")
    page.goto("https://luckymustard.uk/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('input#username', timeout=15000)
    page.locator('input#username').fill(EMAIL)
    page.locator('input#password').fill(PASSWORD)
    page.locator('button[type="submit"]:has-text("ログイン")').click()
    page.wait_for_url("**/admin/**", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)


def fetch_all_pages(page, base_url: str, label: str) -> list:
    """ページネーション付き API を全件取得。"""
    all_items = []
    page_num = 1
    while True:
        url = f"{base_url}{'&' if '?' in base_url else '?'}page={page_num}"
        body = page.evaluate(
            """async (u) => {
                const csrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/)||[])[1]||'');
                const r = await fetch(u, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Accept': 'application/json', 'X-XSRF-TOKEN': csrf, 'X-Requested-With': 'XMLHttpRequest' },
                });
                return { status: r.status, body: await r.json().catch(()=>null) };
            }""", url,
        )
        if body.get("status") != 200 or not body.get("body"):
            print(f"  [{label}] page {page_num}: HTTP {body.get('status')}")
            break
        data = body["body"].get("data", {})
        items = data.get("data", [])
        last_page = data.get("last_page", page_num)
        total = data.get("total", "?")
        all_items.extend(items)
        if page_num == 1:
            print(f"  [{label}] last_page={last_page}, total={total}")
        if page_num >= last_page or not items:
            break
        page_num += 1
    print(f"  [{label}] retrieved {len(all_items)} items in {page_num} pages")
    return all_items


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        print("[1] login...")
        login(page)
        print(f"    OK")

        # ── 取引履歴を全部取る ────────────────
        print("\n[2] fetching ALL transactions-history pages...")
        txns = fetch_all_pages(page, "https://luckymustard.uk/admin/get-transactions-history?keyword=", "transactions")

        if txns:
            print(f"\n  全 transaction: {len(txns)} 件")
            # type 別カウント
            types = Counter(t.get("type") for t in txns)
            print(f"  type 別件数 (上位20):")
            for t, c in types.most_common(20):
                # サンプル1件
                sample = next((tx for tx in txns if tx.get("type") == t), {})
                amount = sample.get("amount", "")
                print(f"    type={t:<8} → {c} 件   sample(amount={amount}, id={sample.get('id')}, from_id={sample.get('from_id')})")
                if c > 0:
                    print(f"       keys: {list(sample.keys())[:15]}")

            # 全カラム名
            all_keys = set()
            for t in txns[:50]:
                all_keys.update(t.keys())
            print(f"\n  全カラム: {sorted(all_keys)}")

            # 保存
            os.makedirs("exports", exist_ok=True)
            with open("exports/_lucky_transactions_raw.json", "w", encoding="utf-8") as f:
                json.dump(txns, f, ensure_ascii=False, indent=2)
            print(f"  → exports/_lucky_transactions_raw.json")

        # ── lucNFT購入 / specialNFT購入 ページを開いて取得 ──
        print("\n[3] visiting /admin/lucky-mustard (lucNFT購入)...")
        page.goto("https://luckymustard.uk/admin/lucky-mustard", wait_until="networkidle", timeout=20000)
        lucky_buys = fetch_all_pages(page, "https://luckymustard.uk/admin/lucky-mustard/get-buy-nft", "lucky-buys")
        if lucky_buys:
            print(f"  sample lucky purchase: {json.dumps(lucky_buys[0], ensure_ascii=False)[:300]}")
            print(f"  keys: {list(lucky_buys[0].keys()) if lucky_buys else 'N/A'}")
            with open("exports/_lucky_buys_raw.json", "w", encoding="utf-8") as f:
                json.dump(lucky_buys, f, ensure_ascii=False, indent=2)

        print("\n[4] visiting /admin/special-mustard (specialNFT購入)...")
        page.goto("https://luckymustard.uk/admin/special-mustard", wait_until="networkidle", timeout=20000)
        special_buys = fetch_all_pages(page, "https://luckymustard.uk/admin/special-mustard/get-buy-nft", "special-buys")
        if special_buys:
            print(f"  sample special purchase: {json.dumps(special_buys[0], ensure_ascii=False)[:300]}")
            print(f"  keys: {list(special_buys[0].keys()) if special_buys else 'N/A'}")
            with open("exports/_special_buys_raw.json", "w", encoding="utf-8") as f:
                json.dump(special_buys, f, ensure_ascii=False, indent=2)

        browser.close()


if __name__ == "__main__":
    main()
