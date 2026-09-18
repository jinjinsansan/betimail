"""定期ジョブと本番状態の見張り番。異常があれば Telegram に通知する。

背景: afi / nftportal のスクレイピング cron が 850 回連続で失敗しても
5 日間誰も気づかなかった（PROJECT_STATE §22.3）。承認待ちの返信が
4 か月放置されていたのも同じ理由（§22 の診断）。
「失敗しても誰にも届かない」状態を潰すために、状態のほうを定期的に見に行く。

チェック内容:
  1. DB バックアップが新しいか（既定 30 時間以内）
  2. ラッキー報酬の分配が滞っていないか（既定 2 日以内）
  3. 一括送信ジョブが running のまま固まっていないか（既定 3 時間）
  4. 承認待ちの AI 返信が放置されていないか（既定 48 時間）
  5. API が生きているか（/health）
  6. ディスクに余裕があるか（既定 85%）

同じ警告を毎時鳴らさないよう、一度通知した項目は既定 24 時間抑止する。

例:
  python tools/health_watchdog.py --notify-telegram
  python tools/health_watchdog.py                  # 表示のみ
  python tools/health_watchdog.py --force-notify   # 抑止を無視して通知（動作確認用）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

DB_PATH = Path(os.getenv("BETIMAIL_DB_PATH", "/app/data/betimail.db"))
BACKUP_DIR = Path(os.getenv("BETIMAIL_BACKUP_DIR", "/app/data/backups"))
STATE_PATH = Path(os.getenv("BETIMAIL_WATCHDOG_STATE", "/app/data/watchdog_state.json"))
HEALTH_URL = os.getenv("BETIMAIL_HEALTH_URL", "http://127.0.0.1:8000/health")


def _now() -> datetime:
    return datetime.now(JST)


def telegram_notify(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("telegram not configured; skipped")
        return
    try:
        chat_id_first = chat_id.split(",")[0].strip()
        data = urllib.parse.urlencode({"chat_id": chat_id_first, "text": text}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10
        ).read()
    except Exception as e:
        print(f"telegram notify failed: {e}")


def _parse_dt(value: str | None) -> datetime | None:
    """DB に入っている ISO 文字列 / 'YYYY-MM-DD HH:MM:SS' を JST として読む。"""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    return None


# ── 各チェック。問題があれば説明文字列を返し、正常なら None ──────────────


def check_backup(max_age_hours: float) -> str | None:
    files = sorted(BACKUP_DIR.glob("betimail_*.db.gz"))
    if not files:
        return f"DB バックアップが 1 つもありません（{BACKUP_DIR}）"
    newest = max(files, key=lambda p: p.stat().st_mtime)
    age_h = (datetime.now(timezone.utc).timestamp() - newest.stat().st_mtime) / 3600
    if age_h > max_age_hours:
        return f"DB バックアップが {age_h:.0f} 時間前から更新されていません（最新 {newest.name}）"
    return None


def check_lucky_distribution(conn: sqlite3.Connection, max_age_days: int) -> str | None:
    row = conn.execute(
        "SELECT max(distributed_for) FROM lucky_distributions WHERE status = 'done'"
    ).fetchone()
    last = _parse_dt(row[0] if row else None)
    if last is None:
        return "ラッキー報酬の分配履歴がありません"
    age_d = (_now() - last).days
    if age_d > max_age_days:
        return f"ラッキー報酬の分配が {age_d} 日止まっています（最終 {row[0]}）"
    return None


def check_stuck_bulk_jobs(conn: sqlite3.Connection, max_hours: float) -> str | None:
    stuck = []
    for row in conn.execute(
        "SELECT id, subject, sent, total, created_at FROM bulk_send_jobs WHERE status = 'running'"
    ):
        started = _parse_dt(row[4])
        if started is None or (_now() - started).total_seconds() / 3600 > max_hours:
            stuck.append(f"#{row[0]} {row[1][:20]} ({row[2]}/{row[3]})")
    if stuck:
        return (
            "一括送信ジョブが running のまま止まっています: "
            + ", ".join(stuck)
            + "\n（再ビルドで送信スレッドが死んだ可能性。差分送信で復旧してください）"
        )
    return None


def check_pending_approvals(conn: sqlite3.Connection, max_hours: float) -> str | None:
    row = conn.execute(
        "SELECT count(*), min(created_at) FROM pending_approvals WHERE status = 'waiting'"
    ).fetchone()
    count = row[0] if row else 0
    if not count:
        return None
    oldest = _parse_dt(row[1])
    if oldest is None:
        return None
    age_h = (_now() - oldest).total_seconds() / 3600
    if age_h > max_hours:
        return (
            f"承認待ちの返信が {count} 件、最古は {age_h / 24:.0f} 日前から未対応です"
            "\n（会員は返信を待っています。管理画面の承認タブを確認してください）"
        )
    return None


def check_health() -> str | None:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=10) as r:
            if r.status != 200:
                return f"API のヘルスチェックが {r.status} を返しました"
    except Exception as e:
        return f"API に到達できません: {type(e).__name__}: {e}"
    return None


def check_disk(max_percent: float) -> str | None:
    usage = shutil.disk_usage(str(DB_PATH.parent))
    percent = usage.used / usage.total * 100
    if percent > max_percent:
        return f"ディスク使用率が {percent:.0f}% です（残り {usage.free / 1024**3:.1f}GB）"
    return None


# ── 通知の抑止 ────────────────────────────────────────────────


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"state save failed: {e}")


def _should_notify(state: dict, key: str, suppress_hours: float, force: bool) -> bool:
    if force:
        return True
    last = _parse_dt(state.get(key))
    if last is None:
        return True
    return (_now() - last).total_seconds() / 3600 >= suppress_hours


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--notify-telegram", action="store_true")
    p.add_argument("--force-notify", action="store_true", help="抑止を無視して通知（動作確認用）")
    p.add_argument("--backup-max-age-hours", type=float, default=30.0)
    p.add_argument("--lucky-max-age-days", type=int, default=2)
    p.add_argument("--bulk-stuck-hours", type=float, default=3.0)
    p.add_argument("--approval-max-age-hours", type=float, default=48.0)
    p.add_argument("--disk-max-percent", type=float, default=85.0)
    p.add_argument("--suppress-hours", type=float, default=24.0)
    args = p.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        checks = [
            ("backup", check_backup(args.backup_max_age_hours)),
            ("lucky", check_lucky_distribution(conn, args.lucky_max_age_days)),
            ("bulk", check_stuck_bulk_jobs(conn, args.bulk_stuck_hours)),
            ("approvals", check_pending_approvals(conn, args.approval_max_age_hours)),
            ("health", check_health()),
            ("disk", check_disk(args.disk_max_percent)),
        ]
    finally:
        conn.close()

    ts = _now().strftime("%Y-%m-%d %H:%M:%S")
    problems = [(key, msg) for key, msg in checks if msg]
    for key, msg in checks:
        print(f"[{ts}] {key}: {'NG ' + msg.splitlines()[0] if msg else 'ok'}")

    if not problems:
        return 0

    state = _load_state()
    to_send = [
        (key, msg)
        for key, msg in problems
        if _should_notify(state, key, args.suppress_hours, args.force_notify)
    ]
    if to_send and args.notify_telegram:
        body = "\n\n".join(f"・{msg}" for _, msg in to_send)
        telegram_notify(f"⚠️ betimail 監視で異常を検知しました（{ts}）\n\n{body}")
        for key, _ in to_send:
            state[key] = _now().strftime("%Y-%m-%d %H:%M:%S")
        _save_state(state)
    elif to_send:
        print("(--notify-telegram が無いため通知しません)")
    else:
        print("(すべて抑止期間内のため通知しません)")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
