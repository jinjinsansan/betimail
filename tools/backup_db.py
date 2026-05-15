"""SQLite バックアップ作成スクリプト。

例:
  python tools/backup_db.py
  python tools/backup_db.py --verify --keep 30
"""
from __future__ import annotations

import argparse
import gzip
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _default_db_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    return Path(os.getenv("BETIMAIL_DB_PATH", str(root / "data" / "betimail.db")))


def _default_backup_dir() -> Path:
    return Path(os.getenv("BETIMAIL_BACKUP_DIR", "/opt/betimail/backups"))


def _backup_name() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"betimail_{ts}.db.gz"


def _verify_sqlite(path: Path) -> None:
    with sqlite3.connect(str(path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
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

    with sqlite3.connect(str(db_path)) as src, sqlite3.connect(str(temp_copy)) as dst:
        src.backup(dst)

    if verify:
        _verify_sqlite(temp_copy)

    with temp_copy.open("rb") as rf, gzip.open(gz_path, "wb", compresslevel=6) as wf:
        wf.write(rf.read())
    temp_copy.unlink(missing_ok=True)

    _prune_old_backups(backup_dir, keep=max(1, keep))
    return gz_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(_default_db_path()), help="SQLite DB path")
    p.add_argument("--out-dir", default=str(_default_backup_dir()), help="Backup output directory")
    p.add_argument("--keep", type=int, default=14, help="How many backup files to keep")
    p.add_argument("--verify", action="store_true", help="Run SQLite integrity_check before compressing")
    args = p.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    out = create_backup(db_path, out_dir, keep=args.keep, verify=args.verify)
    print(f"backup_created={out}")


if __name__ == "__main__":
    main()
