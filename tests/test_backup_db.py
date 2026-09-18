"""DB バックアップ (tools/backup_db.py) のテスト。

バックアップは障害時の最後の砦なので、
「壊れた DB を素通しにしない」「古い世代を消しすぎない」を押さえる。
"""
import gzip
import sqlite3

import pytest

from tools.backup_db import _prune_old_backups, _verify_sqlite, create_backup


def _make_db(path, rows=3):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"v{i}",) for i in range(rows)])
        conn.commit()
    finally:
        conn.close()
    return path


def test_create_backup_roundtrip(tmp_path):
    db_path = _make_db(tmp_path / "src.db", rows=5)
    out_dir = tmp_path / "backups"

    gz = create_backup(db_path, out_dir, keep=14, verify=True)

    assert gz.exists() and gz.suffix == ".gz"
    # 展開して中身が読めること（= 実際に復元できる）
    restored = tmp_path / "restored.db"
    with gzip.open(gz, "rb") as rf:
        restored.write_bytes(rf.read())
    conn = sqlite3.connect(str(restored))
    try:
        assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 5
    finally:
        conn.close()


def test_temp_copy_is_cleaned_up(tmp_path):
    """中間ファイルが残らないこと（Windows では接続が開いたままだと消せない）。"""
    db_path = _make_db(tmp_path / "src.db")
    out_dir = tmp_path / "backups"

    create_backup(db_path, out_dir, keep=14, verify=True)

    assert not (out_dir / "betimail_tmp_copy.db").exists()


def test_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_backup(tmp_path / "nope.db", tmp_path / "backups", keep=14, verify=True)


def test_verify_rejects_corrupt_db(tmp_path):
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is not a sqlite database")
    with pytest.raises(Exception):
        _verify_sqlite(broken)


def test_prune_keeps_newest_and_ignores_others(tmp_path):
    for day in range(10, 16):
        (tmp_path / f"betimail_202609{day}T000000Z.db.gz").write_bytes(b"x")
    keep_me = tmp_path / "betimail.db.bak-preportal"
    keep_me.write_bytes(b"x")

    _prune_old_backups(tmp_path, keep=3)

    left = sorted(p.name for p in tmp_path.glob("betimail_*.db.gz"))
    assert left == [
        "betimail_20260913T000000Z.db.gz",
        "betimail_20260914T000000Z.db.gz",
        "betimail_20260915T000000Z.db.gz",
    ]
    # 手動で取った移行前バックアップを巻き込まないこと
    assert keep_me.exists()
