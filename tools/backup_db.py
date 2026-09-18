"""SQLite バックアップ作成スクリプト。

例:
  python tools/backup_db.py
  python tools/backup_db.py --verify --keep 30
  python tools/backup_db.py --verify --keep 14 --notify-telegram

cron から回す場合、出力先はコンテナ外へ永続化される場所を指定すること
（コンテナ内の /opt/betimail/backups は再ビルドで消える）:
  docker exec betimail python /app/tools/backup_db.py       --verify --keep 14 --out-dir /app/data/backups --notify-telegram
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _default_db_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    return Path(os.getenv("BETIMAIL_DB_PATH", str(root / "data" / "betimail.db")))


def _default_backup_dir() -> Path:
    return Path(os.getenv("BETIMAIL_BACKUP_DIR", "/opt/betimail/backups"))


def telegram_notify(text: str) -> None:
    """失敗を仁氏の Telegram に飛ばす。通知自体の失敗は握りつぶす。"""
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
        print(f"telegram notify failed: {e}", flush=True)


def _backup_name() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"betimail_{ts}.db.gz"


def _verify_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    if not result or result[0] != "ok":
        raise RuntimeError(f"SQLite integrity_check failed: {result}")


def _prune_old_backups(backup_dir: Path, keep: int) -> None:
    files = sorted(backup_dir.glob("betimail_*.db.gz"), key=lambda p: p.name, reverse=True)
    for p in files[keep:]:
        p.unlink(missing_ok=True)


def create_backup(db_path: Path, backup_dir: Path, keep: int, verify: bool) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    backup_dir.mkdir(parents=True, exist_ok=True)

    temp_copy = backup_dir / "betimail_tmp_copy.db"
    gz_path = backup_dir / _backup_name()

    # sqlite3 の with は commit するだけで close しない。閉じないと Windows で
    # temp_copy を unlink できず、Linux でもハンドルが残る。
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(temp_copy))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    if verify:
        _verify_sqlite(temp_copy)

    # 72MB の DB を丸ごとメモリに載せないようストリーミングで圧縮する（VPS は 2GB）
    with temp_copy.open("rb") as rf, gzip.open(gz_path, "wb", compresslevel=6) as wf:
        shutil.copyfileobj(rf, wf, length=1024 * 1024)
    temp_copy.unlink(missing_ok=True)

    _prune_old_backups(backup_dir, keep=max(1, keep))
    return gz_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(_default_db_path()), help="SQLite DB path")
    p.add_argument("--out-dir", default=str(_default_backup_dir()), help="Backup output directory")
    p.add_argument("--keep", type=int, default=14, help="How many backup files to keep")
    p.add_argument("--verify", action="store_true", help="Run SQLite integrity_check before compressing")
    p.add_argument("--notify-telegram", action="store_true", help="Notify Telegram when the backup fails")
    p.add_argument("--notify-success", action="store_true", help="Also notify Telegram on success")
    args = p.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    try:
        out = create_backup(db_path, out_dir, keep=args.keep, verify=args.verify)
    except Exception as e:
        print(f"[{ts}] backup_failed: {type(e).__name__}: {e}", flush=True)
        if args.notify_telegram:
            telegram_notify(f"❌ DB バックアップ失敗\n{type(e).__name__}: {e}")
        raise
    size_mb = out.stat().st_size / 1024 / 1024
    generations = len(list(out_dir.glob("betimail_*.db.gz")))
    print(f"[{ts}] backup_created={out} size={size_mb:.1f}MB generations={generations}")
    if args.notify_success and args.notify_telegram:
        telegram_notify(
            f"✅ DB バックアップ完了\n{out.name}\n{size_mb:.1f}MB / 保持 {generations} 世代"
        )


if __name__ == "__main__":
    main()
