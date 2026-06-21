"""nftportal.site から最新の出金申請を取得し、DB に同期する。

- 既存 external_id があれば更新
- 無ければ新規挿入 + Telegram 通知用にマーク (notified_at NULL)
- 通知未済を一気に Telegram に投げる

定期実行用:
    python sync_nftportal_withdraws.py --start-year 2025 --start-month 11 --notify-telegram

初回 backfill (履歴フラグ):
    python sync_nftportal_withdraws.py --backfill   # 取り込みのみ、通知済み扱い
"""
import argparse
import json
import os
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = Path("/opt/betimail/logs/nftportal_sync")
LOG_FILE = LOG_DIR / "sync.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_KEEP = 5


def _rotate_log_file(path: Path, max_bytes: int = LOG_MAX_BYTES, keep: int = LOG_KEEP) -> None:
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    for i in range(keep - 1, 0, -1):
        src = path.with_name(f"{path.name}.{i}")
        dst = path.with_name(f"{path.name}.{i + 1}")
        if src.exists():
            src.replace(dst)
    path.replace(path.with_name(f"{path.name}.1"))


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _rotate_log_file(LOG_FILE)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def telegram_send(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log("telegram: BOT_TOKEN/CHAT_ID 未設定、スキップ")
        return False
    try:
        chat_id_first = chat_id.split(",")[0].strip()
        data = urllib.parse.urlencode({
            "chat_id": chat_id_first, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10
        ) as r:
            return r.status == 200
    except Exception as e:
        log(f"telegram send failed: {e}")
        return False


def _playwright_goto_with_retry(page, url: str, wait_until: str = "domcontentloaded",
                                timeout: int = 60000, max_retries: int = 2) -> None:
    """page.goto をリトライ付きで実行。初回失敗時に5秒待って再試行。"""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                log(f"goto {url} attempt {attempt+1} failed ({e}), retrying in 5s...")
                page.wait_for_timeout(5000)
    raise last_exc  # type: ignore[misc]


def fetch_withdraws_via_playwright(start_year: int, start_month: int) -> list[dict]:
    """Playwright で login → withdraw-history を月ごとに取得。"""
    from playwright.sync_api import sync_playwright

    email = os.getenv("NFTPORTAL_ADMIN_EMAIL", "")
    password = os.getenv("NFTPORTAL_ADMIN_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("NFTPORTAL_ADMIN_EMAIL / PASSWORD 未設定")

    all_items = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        # domcontentloaded で十分（ログインフォームが出れば OK）
        _playwright_goto_with_retry(page, "https://nftportal.site/auth/login",
                                    wait_until="domcontentloaded", timeout=60000)
        page.locator('input#username').fill(email)
        page.locator('input#password').fill(password)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_timeout(2500)
        _playwright_goto_with_retry(page, "https://nftportal.site/admin/withdraw-history",
                                    wait_until="domcontentloaded", timeout=60000)

        now = datetime.now()
        cy, cm = start_year, start_month
        while (cy, cm) <= (now.year, now.month):
            body = page.evaluate(
                """async ({url, body}) => {
                    const csrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/)||[])[1]||'');
                    const r = await fetch(url, {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json',
                            'X-XSRF-TOKEN': csrf,
                            'X-Requested-With': 'XMLHttpRequest',
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(body),
                    });
                    return { status: r.status, body: await r.json().catch(()=>null) };
                }""",
                {
                    "url": "https://nftportal.site/admin/withdraw-history/get-data?page=1",
                    "body": {"keyword": "", "month": cm, "year": cy},
                },
            )
            if body.get("status") == 200 and body.get("body"):
                items = body["body"].get("data", {}).get("data", []) or []
                all_items.extend(items)
            # next month
            if cm == 12:
                cm = 1; cy += 1
            else:
                cm += 1
        browser.close()
    return all_items


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start-year", type=int, default=2025)
    p.add_argument("--start-month", type=int, default=11)
    p.add_argument("--notify-telegram", action="store_true")
    p.add_argument("--backfill", action="store_true",
                   help="初回投入。既存記録を未通知扱いにしないよう notified_at をすぐ埋める")
    args = p.parse_args()

    # /opt/betimail/.env を読み込む
    env_file = Path("/opt/betimail/.env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    log(f"=== sync start (start={args.start_year}-{args.start_month:02d}, "
        f"notify={args.notify_telegram}, backfill={args.backfill}) ===")

    try:
        records = fetch_withdraws_via_playwright(args.start_year, args.start_month)
    except Exception as e:
        log(f"fetch failed: {e}\n{traceback.format_exc()}")
        if args.notify_telegram:
            telegram_send(f"❌ nftportal sync 失敗: {e}")
        sys.exit(1)
    log(f"fetched {len(records)} withdraw records")

    import db
    db.init_db()

    new_count = 0
    for r in records:
        rec = {
            "external_id": r.get("id"),
            "email": (r.get("email") or "").strip().lower(),
            "name": r.get("name"),
            "user_id": r.get("user_id"),
            "amount_usdt": float(r.get("amount") or 0),
            "destination": r.get("destination"),
            "type": r.get("type"),
            "status": r.get("status"),
            "requested_at": r.get("created_at"),
            "action_at": r.get("action_at"),
            "secret_code": r.get("secret_code"),
            "packet": r.get("packet"),
            "title": r.get("title"),
            "raw_json": json.dumps(r, ensure_ascii=False),
        }
        is_new = db.upsert_withdraw(rec)
        if is_new:
            new_count += 1
            if args.backfill:
                # 初回バックフィルは通知済み扱い
                db.mark_withdraw_notified(rec["external_id"])
    log(f"new records: {new_count}")

    # 通知未済を Telegram へ
    if args.notify_telegram and not args.backfill:
        unnotified = db.unnotified_withdraws()
        log(f"unnotified: {len(unnotified)}")
        for w in unnotified:
            msg = (
                f"💰 <b>新しい買い取り出金申請</b>\n"
                f"申請者: {w.get('name','?')} &lt;{w.get('email')}&gt;\n"
                f"金額: {w.get('amount_usdt')} USDT\n"
                f"申請日: {w.get('requested_at','')[:16]}\n"
                f"宛先: <code>{w.get('destination','')[:42]}</code>\n"
                f"status: {w.get('status')}"
            )
            if telegram_send(msg):
                db.mark_withdraw_notified(w["external_id"])
                log(f"notified external_id={w['external_id']}")

    log(f"=== sync done. total in db: {len(db.list_withdraws(limit=10000))} ===")


if __name__ == "__main__":
    main()
