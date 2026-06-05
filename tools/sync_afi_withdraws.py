"""afi.irah.uk の出金申請を取得し、DB (withdraw_requests, source='afi') に同期する。

- afi.irah.uk/admin/get-withdraw-requests は **POST**・月単位 (year/month 必須)。
- `req_id` が出金申請の一意 id（`id` はユーザー単位で重複するため使わない）。
  nftportal の external_id (8〜26) と数値が衝突するため、AFI は AFI_ID_OFFSET を
  足して external_id を名前空間分離する。元の req_id は raw_json に保持。
- `status_request`: 1=未承認(未処理, action_at なし) / 2=承認済。これを status 列へ。

定期実行 (cron):
    python sync_afi_withdraws.py --notify-telegram
初回バックフィル (履歴を通知せず取り込み):
    python sync_afi_withdraws.py --backfill
"""
import argparse
import json
import os
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# nftportal(8〜26) と衝突しないよう AFI の req_id を offset する
AFI_ID_OFFSET = 1_000_000_000

LOG_DIR = Path("/opt/betimail/logs/afi_sync")
LOG_FILE = LOG_DIR / "sync.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_KEEP = 5

START_YEAR_DEFAULT = 2024
START_MONTH_DEFAULT = 1


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


def fetch_withdraws_via_playwright(start_year: int, start_month: int) -> list[dict]:
    """Playwright で afi にログイン → get-withdraw-requests を月毎に POST 取得。"""
    from playwright.sync_api import sync_playwright

    email = os.getenv("AFI_ADMIN_EMAIL", "")
    password = os.getenv("AFI_ADMIN_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("AFI_ADMIN_EMAIL / AFI_ADMIN_PASSWORD 未設定")

    def call(page, url):
        return page.evaluate(
            """async (u) => {
                const csrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/)||[])[1]||'');
                const r = await fetch(u, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json',
                        'X-XSRF-TOKEN': csrf,
                        'X-Requested-With': 'XMLHttpRequest',
                        'Content-Type': 'application/json',
                    },
                    body: '{}',
                });
                return { status: r.status, body: await r.json().catch(() => null) };
            }""",
            url,
        )

    all_items: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        page.goto("https://afi.irah.uk/auth/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("input#username", timeout=15000)
        page.locator("input#username").fill(email)
        page.locator("input#password").fill(password)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_url("**/admin/**", timeout=20000)
        page.wait_for_load_state("networkidle", timeout=15000)

        now = datetime.now()
        cy, cm = start_year, start_month
        while (cy, cm) <= (now.year, now.month):
            pg = 1
            while True:
                url = (
                    f"https://afi.irah.uk/admin/get-withdraw-requests"
                    f"?page={pg}&year={cy}&month={cm}&keyword="
                )
                res = call(page, url)
                if res.get("status") != 200 or not res.get("body"):
                    break
                data = res["body"].get("data", {})
                items = data.get("data", []) if isinstance(data, dict) else []
                all_items.extend(items)
                last_page = data.get("last_page", pg) if isinstance(data, dict) else pg
                if pg >= last_page or not items:
                    break
                pg += 1
            if cm == 12:
                cm = 1; cy += 1
            else:
                cm += 1
        browser.close()
    return all_items


def _to_record(r: dict) -> dict:
    req_id = r.get("req_id")
    return {
        "external_id": AFI_ID_OFFSET + int(req_id) if req_id is not None else None,
        "source": "afi",
        "email": (r.get("email") or "").strip().lower(),
        "name": r.get("name"),
        "user_id": r.get("user_id"),
        "amount_usdt": float(r.get("amount") or 0),
        "destination": r.get("wallet_address"),
        "type": None,
        "status": r.get("status_request"),  # 1=未承認 / 2=承認済
        "requested_at": r.get("created_at"),
        "action_at": r.get("action_at"),
        "secret_code": r.get("secret_code"),
        "title": r.get("title"),
        "nft_kind": "会員権NFT",
        "raw_json": json.dumps(r, ensure_ascii=False),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start-year", type=int, default=START_YEAR_DEFAULT)
    p.add_argument("--start-month", type=int, default=START_MONTH_DEFAULT)
    p.add_argument("--notify-telegram", action="store_true")
    p.add_argument("--backfill", action="store_true",
                   help="初回投入。新規でも通知せず notified_at を即埋める")
    args = p.parse_args()

    env_file = Path("/opt/betimail/.env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    log(f"=== AFI sync start (start={args.start_year}-{args.start_month:02d}, "
        f"notify={args.notify_telegram}, backfill={args.backfill}) ===")

    try:
        records = fetch_withdraws_via_playwright(args.start_year, args.start_month)
    except Exception as e:
        log(f"fetch failed: {e}\n{traceback.format_exc()}")
        if args.notify_telegram:
            telegram_send(f"❌ AFI 出金 sync 失敗: {e}")
        sys.exit(1)
    log(f"fetched {len(records)} AFI withdraw records")

    import db
    db.init_db()

    new_count = 0
    new_pending: list[dict] = []
    for r in records:
        rec = _to_record(r)
        if rec["external_id"] is None:
            continue
        is_new = db.upsert_withdraw(rec)
        if is_new:
            new_count += 1
            if args.backfill:
                # 初回バックフィルは通知せず通知済み扱い
                db.mark_withdraw_notified(rec["external_id"])
            else:
                # 新着は通知後に必ず notified_at を埋める（source 跨ぎの誤通知防止）
                if str(rec.get("status")) == "1":  # 未承認のみ通知
                    new_pending.append(rec)
                else:
                    db.mark_withdraw_notified(rec["external_id"])
    log(f"new records: {new_count} (new pending to notify: {len(new_pending)})")

    if args.notify_telegram and not args.backfill:
        for rec in new_pending:
            req_id = (rec["external_id"] - AFI_ID_OFFSET) if rec["external_id"] else "?"
            msg = (
                f"💸 <b>AFI 新しい未承認の出金申請</b>\n"
                f"申請者: {rec.get('name', '?')} &lt;{rec.get('email')}&gt;\n"
                f"金額: {rec.get('amount_usdt')} USDT\n"
                f"申請日: {str(rec.get('requested_at') or '')[:16]}\n"
                f"宛先: <code>{str(rec.get('destination') or '')[:42]}</code>\n"
                f"req_id: {req_id} / status: 未承認"
            )
            if telegram_send(msg):
                db.mark_withdraw_notified(rec["external_id"])
                log(f"notified req_id={req_id}")
            else:
                # 送信失敗でも通知済みにして二重送信を避ける（次回も新着なら拾える）
                db.mark_withdraw_notified(rec["external_id"])
                log(f"notify failed but marked req_id={req_id}")

    afi_total = len([w for w in db.list_withdraws(limit=100000) if w.get("source") == "afi"])
    log(f"=== AFI sync done. afi rows in db: {afi_total} ===")


if __name__ == "__main__":
    main()
