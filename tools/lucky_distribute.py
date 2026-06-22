"""ラッキーマスタード 日次報酬分配（DB内・サイト非依存）。

元サイト luckymustard.uk が恒久ダウンしたため、Playwright で死んだサイトを叩く
daily_lucky_reward.py の代替。betimail の DB 内で報酬分配を実行する。

  分配額（1会員）= round(保有ステークNFT枚数 × 日次プール ÷ 総NFT枚数, 2)

毎日 20:00 JST に cron（betimail コンテナ内 docker exec）で実行する想定。

実行例:
    python tools/lucky_distribute.py --notify-telegram
        → 本日(JST)分を分配（既に分配済みならスキップ）
    python tools/lucky_distribute.py --backfill-from 2026-06-11 --notify-telegram
        → 6/11〜本日のうち未分配の日をまとめて分配（停止期間の補填）
    python tools/lucky_distribute.py --date 2026-06-15 --dry-run
        → 指定日を試算（DB 書き込みなし）

環境変数:
    LUCKY_DAILY_AMOUNT (default 352)   日次プール総額 (USDT)
    LUCKY_DAILY_MIN_AMOUNT / MAX_AMOUNT (default 1 / 5000)
    TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
    LUCKY_LOG_DIR (default /opt/betimail/logs/lucky_distribute)
    BETIMAIL_DB_PATH (betimail コンテナ内は config 既定の data/betimail.db)
"""
import argparse
import datetime as dt
import json
import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JST = dt.timezone(dt.timedelta(hours=9))
LOG_DIR = Path(os.getenv("LUCKY_LOG_DIR", "/opt/betimail/logs/lucky_distribute"))
LOG_FILE = LOG_DIR / "distribute.log"
LOCK_FILE = LOG_DIR / ".lucky_distribute.lock"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_KEEP = 5
DISTRIBUTE_TIME = "20:00:00"  # JST。元サイトの分配時刻に合わせる


class AlreadyRunningError(RuntimeError):
    pass


def _rotate_log_file(path: Path) -> None:
    if not path.exists() or path.stat().st_size < LOG_MAX_BYTES:
        return
    for i in range(LOG_KEEP - 1, 0, -1):
        src = path.with_name(f"{path.name}.{i}")
        dst = path.with_name(f"{path.name}.{i + 1}")
        if src.exists():
            src.replace(dst)
    path.replace(path.with_name(f"{path.name}.1"))


def log(msg: str) -> None:
    ts = dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _rotate_log_file(LOG_FILE)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # ログ書込み失敗は致命的でない


def telegram_notify(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        import urllib.request
        import urllib.parse
        chat_id_first = chat_id.split(",")[0].strip()
        data = urllib.parse.urlencode({"chat_id": chat_id_first, "text": text}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10
        ).read()
    except Exception as e:
        log(f"telegram notify failed: {e}")


def _today_jst() -> dt.date:
    return dt.datetime.now(JST).date()


def _validate_amount(amount: float) -> None:
    min_amount = float(os.getenv("LUCKY_DAILY_MIN_AMOUNT", "1"))
    max_amount = float(os.getenv("LUCKY_DAILY_MAX_AMOUNT", "5000"))
    if amount < min_amount or amount > max_amount:
        raise ValueError(
            f"amount={amount} は許容範囲外です ({min_amount}〜{max_amount}, "
            f"env: LUCKY_DAILY_MIN_AMOUNT/MAX_AMOUNT)"
        )


@contextmanager
def _acquire_run_lock():
    """多重起動防止。fcntl が無い環境(Windows)ではロックなしで続行。"""
    try:
        import fcntl
    except ImportError:
        yield
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_FILE, "w", encoding="utf-8")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AlreadyRunningError("lucky_distribute is already running")
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        fh.close()


def _date_range(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def distribute_one(db, date_str: str, amount: float, *, dry_run: bool, force: bool) -> dict:
    """1 日分の分配。戻り値に status を含む。"""
    if not force and db.lucky_distribution_exists_for_date(date_str):
        return {"date": date_str, "status": "skipped_exists"}
    if dry_run:
        totals = db.lucky_totals()
        total_nft = totals["total_nft"] or 0
        rate = (amount / total_nft) if total_nft else 0
        return {
            "date": date_str, "status": "dry_run",
            "total_nft": total_nft, "recipients": totals["members"],
            "rate": round(rate, 6), "projected_total": round(amount, 2),
        }
    res = db.create_lucky_distribution(
        amount, created_by="cron", distributed_for=f"{date_str} {DISTRIBUTE_TIME}",
    )
    res["date"] = date_str
    res["status"] = "done"
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--amount", type=float, default=None,
                   help="日次プール総額（デフォルト LUCKY_DAILY_AMOUNT または 352）")
    p.add_argument("--date", default=None, help="分配対象日 YYYY-MM-DD（既定: 本日 JST）")
    p.add_argument("--backfill-from", default=None,
                   help="この日付から本日まで未分配日をまとめて分配 YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="DB 書き込みせず試算のみ")
    p.add_argument("--force", action="store_true", help="分配済みの日でも実行する")
    p.add_argument("--notify-telegram", action="store_true")
    args = p.parse_args()

    # cron は .env を読まないので明示ロード（コンテナ内は --env-file 済みで no-op）
    env_file = Path("/opt/betimail/.env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    import db

    amount = args.amount if args.amount is not None else float(os.getenv("LUCKY_DAILY_AMOUNT", "352"))
    try:
        _validate_amount(amount)
    except Exception as e:
        log(f"❌ amount validation error: {e}")
        sys.exit(2)

    today = _today_jst()
    if args.backfill_from:
        try:
            start = dt.date.fromisoformat(args.backfill_from)
        except ValueError:
            log(f"❌ --backfill-from の日付形式が不正: {args.backfill_from}")
            sys.exit(2)
        dates = list(_date_range(start, today))
    else:
        target = dt.date.fromisoformat(args.date) if args.date else today
        dates = [target]

    log(f"=== lucky_distribute start (amount={amount}, days={len(dates)}, "
        f"dry_run={args.dry_run}, force={args.force}) ===")

    results: list[dict] = []
    try:
        db.init_db()
        with _acquire_run_lock():
            for d in dates:
                ds = d.isoformat()
                try:
                    r = distribute_one(db, ds, amount, dry_run=args.dry_run, force=args.force)
                    results.append(r)
                    if r["status"] == "done":
                        log(f"  {ds}: 分配 {r['recipients']}名 / {r['total_nft']}枚 / "
                            f"単価{r['rate']:.4f} / 配布計{r['distributed_total']} USDT")
                    elif r["status"] == "skipped_exists":
                        log(f"  {ds}: 既に分配済みのためスキップ")
                    elif r["status"] == "dry_run":
                        log(f"  {ds}: [DRY] {r['recipients']}名 / {r['total_nft']}枚 / "
                            f"単価{r['rate']:.4f} / 想定計{r['projected_total']} USDT")
                except Exception as e:
                    log(f"  {ds}: ❌ 分配失敗: {e}")
                    results.append({"date": ds, "status": "error", "error": str(e)})
    except AlreadyRunningError:
        msg = "ℹ️ lucky_distribute は既に実行中のためスキップしました"
        log(msg)
        if args.notify_telegram:
            telegram_notify(msg)
        return
    except Exception as e:
        log(f"❌ ERROR: {e}\n{traceback.format_exc()}")
        if args.notify_telegram:
            telegram_notify(f"❌ ラッキー報酬分配 失敗: {e}")
        sys.exit(1)

    done = [r for r in results if r["status"] == "done"]
    errors = [r for r in results if r["status"] == "error"]
    skipped = [r for r in results if r["status"] == "skipped_exists"]
    total_usdt = round(sum(r.get("distributed_total", 0) for r in done), 2)
    log(f"=== done: 分配{len(done)}日 / スキップ{len(skipped)}日 / エラー{len(errors)}日 / "
        f"合計{total_usdt} USDT ===")

    if args.notify_telegram:
        if args.dry_run:
            dr = [r for r in results if r["status"] == "dry_run"]
            telegram_notify(f"ℹ️ ラッキー報酬分配 [DRY-RUN] 対象{len(dr)}日 金額={amount}/日")
        elif errors:
            telegram_notify(
                f"⚠️ ラッキー報酬分配 [要確認] 分配{len(done)}日 エラー{len(errors)}日 "
                f"合計{total_usdt} USDT"
            )
        elif done:
            day_label = f"{done[0]['date']}" if len(done) == 1 else f"{done[0]['date']}〜{done[-1]['date']}"
            telegram_notify(
                f"✅ ラッキー報酬分配 {day_label}（{len(done)}日分）\n"
                f"対象 {done[-1]['recipients']}名 / {done[-1]['total_nft']}枚 / "
                f"合計 {total_usdt} USDT を配布しました"
            )
        elif skipped:
            telegram_notify(f"ℹ️ ラッキー報酬分配: 対象日({len(skipped)}日)は既に分配済みでした")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
