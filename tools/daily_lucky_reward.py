"""ラッキーマスタード 報酬分配の日次自動実行スクリプト。

毎日 20:00 JST に cron から呼び出され、admin 画面の「報酬分配」ボタンをクリックし
モーダルに金額を入力して確定する。

実行例:
    python daily_lucky_reward.py                     # 環境変数 LUCKY_DAILY_AMOUNT (デフォルト 352)
    python daily_lucky_reward.py --amount 352
    python daily_lucky_reward.py --dry-run           # 確定ボタンは押さない（モーダルまで開いて screenshot）
    python daily_lucky_reward.py --amount 352 --notify-telegram

必須環境変数:
    LUCKY_ADMIN_EMAIL
    LUCKY_ADMIN_PASSWORD

任意:
    LUCKY_DAILY_AMOUNT (default 352)
    TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (Telegram通知用)
"""
import argparse
import datetime as dt
import json
import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright


LOG_DIR = Path("/opt/betimail/logs/lucky_reward")
SCREENSHOT_DIR = Path("/opt/betimail/logs/lucky_reward/shots")
LOG_FILE = LOG_DIR / "daily.log"
LOCK_FILE = LOG_DIR / ".daily_lucky_reward.lock"
STATE_FILE = LOG_DIR / "state.json"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_KEEP = 5
JST = dt.timezone(dt.timedelta(hours=9))


class AlreadyRunningError(RuntimeError):
    """同時実行防止ロック取得に失敗した場合。"""


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
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _rotate_log_file(LOG_FILE)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def telegram_notify(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        import urllib.request, urllib.parse
        chat_id_first = chat_id.split(",")[0].strip()
        data = urllib.parse.urlencode({"chat_id": chat_id_first, "text": text}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10
        ).read()
    except Exception as e:
        log(f"telegram notify failed: {e}")


def _today_jst_str() -> str:
    return dt.datetime.now(JST).strftime("%Y-%m-%d")


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _validate_amount(amount: int) -> None:
    min_amount = int(os.getenv("LUCKY_DAILY_MIN_AMOUNT", "1"))
    max_amount = int(os.getenv("LUCKY_DAILY_MAX_AMOUNT", "5000"))
    if amount < min_amount or amount > max_amount:
        raise ValueError(
            f"amount={amount} は許容範囲外です "
            f"({min_amount}〜{max_amount}, env: LUCKY_DAILY_MIN_AMOUNT/MAX_AMOUNT)"
        )


@contextmanager
def _acquire_run_lock():
    import fcntl

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_FILE, "w", encoding="utf-8")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AlreadyRunningError("daily_lucky_reward is already running")
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        fh.close()


def run(amount: int, email: str, password: str, dry_run: bool = False) -> dict:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts_tag = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        # API レスポンスを記録（成否判定用）
        captured: list[dict] = []
        def on_response(res):
            url = res.url
            if "luckymustard" in url and ("reward" in url.lower() or "distribute" in url.lower() or "share" in url.lower()):
                ct = (res.headers.get("content-type") or "").lower()
                try:
                    body = res.json() if "application/json" in ct else None
                except Exception:
                    body = None
                captured.append({"url": url, "status": res.status, "body": body})
        page.on("response", on_response)

        log("step 1: login")
        # リトライ付き goto
        for attempt in range(3):
            try:
                page.goto("https://luckymustard.uk/", wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                if attempt < 2:
                    log(f"goto luckymustard.uk attempt {attempt+1} failed ({e}), retrying in 5s...")
                    page.wait_for_timeout(5000)
                else:
                    raise
        page.wait_for_selector('input#username', timeout=30000)
        page.locator('input#username').fill(email)
        page.locator('input#password').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_url("**/admin/**", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)

        log("step 2: navigate to /admin/lucky-mustard")
        # リトライ付き
        for attempt in range(3):
            try:
                page.goto("https://luckymustard.uk/admin/lucky-mustard", wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                if attempt < 2:
                    log(f"goto /admin/lucky-mustard attempt {attempt+1} failed ({e}), retrying in 5s...")
                    page.wait_for_timeout(5000)
                else:
                    raise
        page.screenshot(path=str(SCREENSHOT_DIR / f"{ts_tag}_01_page.png"), full_page=False)

        log("step 3: click yellow 報酬分配 button (trigger modal)")
        # btn-warning が黄色トリガー
        trigger = page.locator('button.btn-warning:has-text("報酬分配")').first
        trigger.wait_for(state="visible", timeout=10000)
        trigger.click()
        page.wait_for_timeout(800)
        page.screenshot(path=str(SCREENSHOT_DIR / f"{ts_tag}_02_modal_open.png"), full_page=False)

        log(f"step 4: fill amount = {amount}")
        input_field = page.locator('input[type="number"].only-number').first
        input_field.wait_for(state="visible", timeout=5000)
        input_field.fill("")
        input_field.fill(str(amount))
        page.wait_for_timeout(300)
        page.screenshot(path=str(SCREENSHOT_DIR / f"{ts_tag}_03_filled.png"), full_page=False)

        if dry_run:
            log("DRY-RUN: NOT clicking confirm. Closing modal.")
            browser.close()
            return {"status": "dry_run", "amount": amount, "screenshot_tag": ts_tag}

        log("step 5: click red 報酬分配 confirm button")
        confirm = page.locator('button.btn-danger.radius-10:has-text("報酬分配")').first
        confirm.wait_for(state="visible", timeout=5000)
        confirm.click()

        # 応答を待つ
        page.wait_for_timeout(3000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        page.screenshot(path=str(SCREENSHOT_DIR / f"{ts_tag}_04_after_submit.png"), full_page=False)

        log(f"step 6: captured {len(captured)} reward-related API responses")
        for c in captured:
            log(f"   {c['status']} {c['url']} body_keys={list(c['body'].keys()) if isinstance(c.get('body'), dict) else None}")

        # 成否判定: 200 系で success=true の応答があれば OK
        success = False
        for c in captured:
            if 200 <= c["status"] < 300:
                body = c.get("body")
                if isinstance(body, dict):
                    if body.get("success") is True or body.get("status") == "success":
                        success = True
                        break
                else:
                    success = True
                    break

        browser.close()
        return {
            "status": "success" if success else "submitted",
            "amount": amount,
            "captured_count": len(captured),
            "captured": captured,
            "screenshot_tag": ts_tag,
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--amount", type=int, default=None, help="分配額（デフォルト LUCKY_DAILY_AMOUNT または 352）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="本日実行済みでも強制実行する")
    p.add_argument("--notify-telegram", action="store_true")
    args = p.parse_args()

    # 環境変数読み込み（VPSでcronで動かす場合、cron は .env 読まないので明示的にロード）
    env_file = Path("/opt/betimail/.env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    email = os.getenv("LUCKY_ADMIN_EMAIL", "")
    password = os.getenv("LUCKY_ADMIN_PASSWORD", "")
    amount = args.amount if args.amount is not None else int(os.getenv("LUCKY_DAILY_AMOUNT", "352"))

    if not email or not password:
        log("❌ LUCKY_ADMIN_EMAIL / LUCKY_ADMIN_PASSWORD が未設定です")
        sys.exit(2)
    try:
        _validate_amount(amount)
    except Exception as e:
        log(f"❌ amount validation error: {e}")
        sys.exit(2)

    log(f"=== daily_lucky_reward start (amount={amount}, dry_run={args.dry_run}, force={args.force}) ===")
    try:
        with _acquire_run_lock():
            today = _today_jst_str()
            state = _load_state()
            if not args.dry_run and not args.force and state.get("last_success_date") == today:
                msg = (
                    f"ℹ️ 本日({today})は既に成功実行済みのためスキップ "
                    f"(tag={state.get('last_success_tag', '-')}, amount={state.get('last_success_amount', '-')})"
                )
                log(msg)
                if args.notify_telegram:
                    telegram_notify(msg)
                return

            result = run(amount, email, password, args.dry_run)
            log(f"=== result: {json.dumps({k: v for k, v in result.items() if k != 'captured'}, ensure_ascii=False)} ===")

            status = result.get("status")
            if status == "success" and not args.dry_run:
                state.update({
                    "last_success_date": today,
                    "last_success_at": dt.datetime.now(JST).isoformat(),
                    "last_success_amount": amount,
                    "last_success_tag": result.get("screenshot_tag"),
                })
                _save_state(state)

            if args.notify_telegram:
                if args.dry_run:
                    telegram_notify(
                        f"ℹ️ ラッキー報酬分配 [DRY-RUN] 金額={amount} status={status} "
                        f"captured={result.get('captured_count', 0)}件 tag={result.get('screenshot_tag', '-')}"
                    )
                elif status == "success":
                    telegram_notify(
                        f"✅ ラッキー報酬分配 [実行] 金額={amount} status={status} "
                        f"captured={result.get('captured_count', 0)}件 tag={result.get('screenshot_tag', '-')}"
                    )
                else:
                    telegram_notify(
                        f"⚠️ ラッキー報酬分配 [要確認] 金額={amount} status={status} "
                        f"captured={result.get('captured_count', 0)}件 tag={result.get('screenshot_tag', '-')}"
                    )

            if not args.dry_run and status != "success":
                log("❌ success 判定できなかったため異常終了します（自動再実行による二重送信防止のため手動確認してください）")
                sys.exit(1)
    except AlreadyRunningError:
        msg = "ℹ️ daily_lucky_reward は既に実行中のためスキップしました"
        log(msg)
        if args.notify_telegram:
            telegram_notify(msg)
    except Exception as e:
        log(f"❌ ERROR: {e}\n{traceback.format_exc()}")
        if args.notify_telegram:
            telegram_notify(f"❌ ラッキー報酬分配 失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
