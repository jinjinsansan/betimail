"""監視 (tools/health_watchdog.py) のテスト。

見張り番が黙ってしまうのが一番困るので、
「異常を異常と言う」「正常を異常と言わない」「同じ警告を鳴らし続けない」を押さえる。
"""
import sqlite3
from datetime import timedelta

import pytest

from tools import health_watchdog as hw


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE lucky_distributions (
            id INTEGER PRIMARY KEY, distributed_for TEXT, status TEXT
        );
        CREATE TABLE bulk_send_jobs (
            id INTEGER PRIMARY KEY, subject TEXT, sent INTEGER, total INTEGER,
            status TEXT, created_at TEXT
        );
        CREATE TABLE pending_approvals (
            id INTEGER PRIMARY KEY, status TEXT, created_at TEXT
        );
        """
    )
    yield c
    c.close()


def _ago(**kw):
    return (hw._now() - timedelta(**kw)).strftime("%Y-%m-%d %H:%M:%S")


# ── バックアップ ────────────────────────────────────────────


def test_backup_missing_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(hw, "BACKUP_DIR", tmp_path)
    assert "1 つもありません" in hw.check_backup(30)


def test_fresh_backup_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(hw, "BACKUP_DIR", tmp_path)
    (tmp_path / "betimail_20260918T000000Z.db.gz").write_bytes(b"x")
    assert hw.check_backup(30) is None


def test_stale_backup_is_reported(tmp_path, monkeypatch):
    import os
    import time

    monkeypatch.setattr(hw, "BACKUP_DIR", tmp_path)
    old = tmp_path / "betimail_20260901T000000Z.db.gz"
    old.write_bytes(b"x")
    stale = time.time() - 60 * 60 * 48
    os.utime(old, (stale, stale))
    assert "更新されていません" in hw.check_backup(30)


# ── ラッキー分配 ────────────────────────────────────────────


def test_recent_distribution_is_ok(conn):
    conn.execute(
        "INSERT INTO lucky_distributions (distributed_for, status) VALUES (?, 'done')",
        (_ago(hours=12),),
    )
    assert hw.check_lucky_distribution(conn, 2) is None


def test_stalled_distribution_is_reported(conn):
    conn.execute(
        "INSERT INTO lucky_distributions (distributed_for, status) VALUES (?, 'done')",
        (_ago(days=5),),
    )
    assert "分配が 5 日止まっています" in hw.check_lucky_distribution(conn, 2)


def test_no_distribution_history_is_reported(conn):
    assert hw.check_lucky_distribution(conn, 2) is not None


# ── 一括送信ジョブ ──────────────────────────────────────────


def test_running_job_within_window_is_ok(conn):
    """送信中のジョブを誤検知すると、まさに送信中に再起動を誘発しかねない。"""
    conn.execute(
        "INSERT INTO bulk_send_jobs (subject, sent, total, status, created_at)"
        " VALUES ('通信', 100, 961, 'running', ?)",
        (_ago(minutes=20),),
    )
    assert hw.check_stuck_bulk_jobs(conn, 3) is None


def test_long_running_job_is_reported(conn):
    conn.execute(
        "INSERT INTO bulk_send_jobs (subject, sent, total, status, created_at)"
        " VALUES ('betiメルマガ通信', 194, 961, 'running', ?)",
        (_ago(hours=9),),
    )
    msg = hw.check_stuck_bulk_jobs(conn, 3)
    assert "194/961" in msg


def test_done_job_is_ignored(conn):
    conn.execute(
        "INSERT INTO bulk_send_jobs (subject, sent, total, status, created_at)"
        " VALUES ('done', 961, 961, 'done', ?)",
        (_ago(days=30),),
    )
    assert hw.check_stuck_bulk_jobs(conn, 3) is None


# ── 承認待ち ────────────────────────────────────────────────


def test_fresh_approval_is_ok(conn):
    conn.execute(
        "INSERT INTO pending_approvals (status, created_at) VALUES ('waiting', ?)",
        (_ago(hours=2),),
    )
    assert hw.check_pending_approvals(conn, 48) is None


def test_abandoned_approval_is_reported(conn):
    """4 か月放置された 5 件を検知できなかったのが今回の反省。"""
    for _ in range(5):
        conn.execute(
            "INSERT INTO pending_approvals (status, created_at) VALUES ('waiting', ?)",
            (_ago(days=120),),
        )
    msg = hw.check_pending_approvals(conn, 48)
    assert "5 件" in msg and "120 日前" in msg


def test_handled_approval_is_ignored(conn):
    conn.execute(
        "INSERT INTO pending_approvals (status, created_at) VALUES ('approved', ?)",
        (_ago(days=120),),
    )
    assert hw.check_pending_approvals(conn, 48) is None


# ── 通知の抑止 ──────────────────────────────────────────────


def test_first_alert_is_sent_then_suppressed():
    state = {}
    assert hw._should_notify(state, "backup", 24, force=False) is True
    state["backup"] = hw._now().strftime("%Y-%m-%d %H:%M:%S")
    assert hw._should_notify(state, "backup", 24, force=False) is False


def test_alert_repeats_after_suppression_window():
    state = {"backup": _ago(hours=25)}
    assert hw._should_notify(state, "backup", 24, force=False) is True


def test_force_ignores_suppression():
    state = {"backup": hw._now().strftime("%Y-%m-%d %H:%M:%S")}
    assert hw._should_notify(state, "backup", 24, force=True) is True
