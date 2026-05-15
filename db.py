import sqlite3
from datetime import datetime
from typing import Optional
from config import DB_PATH
from logging_config import get_logger

log = get_logger(__name__)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ── 初期化 + 簡易マイグレーション ─────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sent_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_email TEXT NOT NULL,
    recipient_name TEXT,
    nft_type TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    resend_id TEXT,
    bulk_job_id INTEGER,
    status TEXT DEFAULT 'sent',
    error TEXT
);

CREATE TABLE IF NOT EXISTS received_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_email TEXT NOT NULL,
    sender_name TEXT,
    subject TEXT,
    body TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    ai_draft TEXT,
    ai_confidence REAL,
    message_id TEXT,
    in_reply_to TEXT
);

CREATE TABLE IF NOT EXISTS pending_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_email_id INTEGER NOT NULL,
    telegram_message_id INTEGER,
    ai_draft TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'waiting',
    handled_at TEXT,
    handled_by TEXT,
    FOREIGN KEY (received_email_id) REFERENCES received_emails(id)
);

CREATE TABLE IF NOT EXISTS bulk_send_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    nft_types TEXT,
    total INTEGER NOT NULL,
    sent INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    name TEXT,
    nft_type TEXT NOT NULL,
    amount_jpy INTEGER,
    units INTEGER,
    team TEXT,
    transaction_id TEXT,
    purchased_at TEXT,
    status TEXT,
    returns_usdt REAL,
    notes TEXT,
    imported_at TEXT NOT NULL,
    source_file TEXT
);

CREATE INDEX IF NOT EXISTS idx_sent_recipient ON sent_emails(recipient_email);
CREATE INDEX IF NOT EXISTS idx_recv_sender ON received_emails(sender_email);
CREATE INDEX IF NOT EXISTS idx_recv_status ON received_emails(status);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON pending_approvals(status);
CREATE INDEX IF NOT EXISTS idx_purchases_email ON purchases(email);
CREATE INDEX IF NOT EXISTS idx_purchases_nft ON purchases(nft_type);
"""


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = _existing_columns(conn, table)
    if column not in cols:
        log.info("Migrating: ALTER TABLE %s ADD COLUMN %s", table, column)
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db() -> None:
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        # 既存DB向けの追加マイグレーション
        _ensure_column(conn, "sent_emails", "resend_id", "resend_id TEXT")
        _ensure_column(conn, "sent_emails", "bulk_job_id", "bulk_job_id INTEGER")
        _ensure_column(conn, "sent_emails", "status", "status TEXT DEFAULT 'sent'")
        _ensure_column(conn, "sent_emails", "error", "error TEXT")
        _ensure_column(conn, "received_emails", "message_id", "message_id TEXT")
        _ensure_column(conn, "received_emails", "in_reply_to", "in_reply_to TEXT")
        _ensure_column(conn, "pending_approvals", "handled_at", "handled_at TEXT")
        _ensure_column(conn, "pending_approvals", "handled_by", "handled_by TEXT")
    log.info("DB initialized at %s", DB_PATH)


# ── 送信メール ──────────────────────────────────────────
def record_sent_email(
    recipient_email: str,
    recipient_name: str,
    nft_type: str,
    subject: str,
    body: str,
    resend_id: Optional[str] = None,
    bulk_job_id: Optional[int] = None,
    status: str = "sent",
    error: Optional[str] = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO sent_emails
               (recipient_email, recipient_name, nft_type, subject, body, sent_at,
                resend_id, bulk_job_id, status, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (recipient_email, recipient_name, nft_type, subject, body,
             datetime.now().isoformat(), resend_id, bulk_job_id, status, error),
        )
        return cur.lastrowid


# ── 受信メール ──────────────────────────────────────────
def record_received_email(
    sender_email: str,
    sender_name: str,
    subject: str,
    body: str,
    ai_draft: Optional[str] = None,
    ai_confidence: Optional[float] = None,
    message_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO received_emails
               (sender_email, sender_name, subject, body, received_at,
                ai_draft, ai_confidence, message_id, in_reply_to)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sender_email, sender_name, subject, body, datetime.now().isoformat(),
             ai_draft, ai_confidence, message_id, in_reply_to),
        )
        return cur.lastrowid


def update_received_status(received_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE received_emails SET status = ? WHERE id = ?", (status, received_id))


# ── 承認待ち ────────────────────────────────────────────
def create_pending_approval(
    received_email_id: int,
    ai_draft: str,
    telegram_message_id: Optional[int] = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO pending_approvals
               (received_email_id, telegram_message_id, ai_draft, created_at)
               VALUES (?, ?, ?, ?)""",
            (received_email_id, telegram_message_id, ai_draft, datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_pending_approval(approval_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT pa.*, re.sender_email, re.sender_name,
                      re.subject as original_subject, re.body as original_body,
                      re.ai_confidence as ai_confidence,
                      re.message_id as original_message_id
               FROM pending_approvals pa
               JOIN received_emails re ON pa.received_email_id = re.id
               WHERE pa.id = ?""",
            (approval_id,),
        ).fetchone()
        return dict(row) if row else None


def list_pending_approvals(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT pa.*, re.sender_email, re.sender_name,
                      re.subject as original_subject, re.body as original_body,
                      re.ai_confidence as ai_confidence
               FROM pending_approvals pa
               JOIN received_emails re ON pa.received_email_id = re.id
               WHERE pa.status = 'waiting'
               ORDER BY pa.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_approval_status(approval_id: int, status: str, handled_by: str = "") -> None:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            """UPDATE pending_approvals
               SET status = ?, handled_at = ?, handled_by = ?
               WHERE id = ?""",
            (status, now, handled_by, approval_id),
        )
        conn.execute(
            """UPDATE received_emails SET status = ?
               WHERE id = (SELECT received_email_id FROM pending_approvals WHERE id = ?)""",
            (status, approval_id),
        )


def update_approval_telegram_message(approval_id: int, telegram_message_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE pending_approvals SET telegram_message_id = ? WHERE id = ?",
            (telegram_message_id, approval_id),
        )


# ── 履歴 ────────────────────────────────────────────────
def get_sent_emails(limit: int = 50, offset: int = 0, search: str = "") -> list[dict]:
    q = "SELECT * FROM sent_emails"
    args: list = []
    if search:
        q += " WHERE recipient_email LIKE ? OR recipient_name LIKE ? OR subject LIKE ?"
        like = f"%{search}%"
        args = [like, like, like]
    q += " ORDER BY sent_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with get_conn() as conn:
        rows = conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]


def count_sent_emails(search: str = "") -> int:
    q = "SELECT COUNT(*) as c FROM sent_emails"
    args: list = []
    if search:
        q += " WHERE recipient_email LIKE ? OR recipient_name LIKE ? OR subject LIKE ?"
        like = f"%{search}%"
        args = [like, like, like]
    with get_conn() as conn:
        return conn.execute(q, args).fetchone()["c"]


def get_received_emails(limit: int = 50, offset: int = 0, search: str = "") -> list[dict]:
    q = "SELECT * FROM received_emails"
    args: list = []
    if search:
        q += " WHERE sender_email LIKE ? OR sender_name LIKE ? OR subject LIKE ?"
        like = f"%{search}%"
        args = [like, like, like]
    q += " ORDER BY received_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with get_conn() as conn:
        rows = conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]


def count_received_emails(search: str = "") -> int:
    q = "SELECT COUNT(*) as c FROM received_emails"
    args: list = []
    if search:
        q += " WHERE sender_email LIKE ? OR sender_name LIKE ? OR subject LIKE ?"
        like = f"%{search}%"
        args = [like, like, like]
    with get_conn() as conn:
        return conn.execute(q, args).fetchone()["c"]


def get_member_history(email: str, limit: int = 50) -> dict:
    """指定アドレスの送受信履歴をまとめて返す。"""
    with get_conn() as conn:
        sent = conn.execute(
            "SELECT * FROM sent_emails WHERE recipient_email = ? ORDER BY sent_at DESC LIMIT ?",
            (email, limit),
        ).fetchall()
        recv = conn.execute(
            "SELECT * FROM received_emails WHERE sender_email = ? ORDER BY received_at DESC LIMIT ?",
            (email, limit),
        ).fetchall()
    return {
        "sent": [dict(r) for r in sent],
        "received": [dict(r) for r in recv],
    }


def get_recent_exchange(sender_email: str, limit: int = 5) -> list[dict]:
    """AI のコンテキスト用に、直近のやり取りを時系列で返す。"""
    with get_conn() as conn:
        sent = conn.execute(
            "SELECT 'sent' AS direction, sent_at AS ts, subject, body FROM sent_emails "
            "WHERE recipient_email = ? ORDER BY sent_at DESC LIMIT ?",
            (sender_email, limit),
        ).fetchall()
        recv = conn.execute(
            "SELECT 'received' AS direction, received_at AS ts, subject, body FROM received_emails "
            "WHERE sender_email = ? ORDER BY received_at DESC LIMIT ?",
            (sender_email, limit),
        ).fetchall()
    combined = [dict(r) for r in sent] + [dict(r) for r in recv]
    combined.sort(key=lambda r: r["ts"])
    return combined[-limit * 2:]


# ── 一括送信ジョブ ──────────────────────────────────────
def create_bulk_job(subject: str, body: str, nft_types: str, total: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO bulk_send_jobs (subject, body, nft_types, total, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (subject, body, nft_types, total, datetime.now().isoformat()),
        )
        return cur.lastrowid


def increment_bulk_job(job_id: int, sent_delta: int = 0, failed_delta: int = 0) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE bulk_send_jobs SET sent = sent + ?, failed = failed + ? WHERE id = ?",
            (sent_delta, failed_delta, job_id),
        )


def finish_bulk_job(job_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE bulk_send_jobs SET status = 'done', finished_at = ? WHERE id = ?",
            (datetime.now().isoformat(), job_id),
        )


def get_bulk_job(job_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bulk_send_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_bulk_jobs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bulk_send_jobs ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── テンプレート ────────────────────────────────────────
def list_templates() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM templates ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_template(name: str, subject: str, body: str) -> int:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM templates WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE templates SET subject = ?, body = ?, updated_at = ? WHERE id = ?",
                (subject, body, now, existing["id"]),
            )
            return existing["id"]
        cur = conn.execute(
            """INSERT INTO templates (name, subject, body, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name, subject, body, now, now),
        )
        return cur.lastrowid


def delete_template(template_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        return cur.rowcount > 0


# ── 購入履歴 ────────────────────────────────────────────
def insert_purchase(record: dict) -> int:
    """単一の購入レコードを挿入。"""
    record.setdefault("imported_at", datetime.now().isoformat())
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO purchases
               (email, name, nft_type, amount_jpy, units, team, transaction_id,
                purchased_at, status, returns_usdt, notes, imported_at, source_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("email", "").strip().lower(),
                record.get("name", ""),
                record.get("nft_type", ""),
                record.get("amount_jpy"),
                record.get("units"),
                record.get("team", ""),
                record.get("transaction_id", ""),
                record.get("purchased_at", ""),
                record.get("status", ""),
                record.get("returns_usdt"),
                record.get("notes", ""),
                record["imported_at"],
                record.get("source_file", ""),
            ),
        )
        return cur.lastrowid


def bulk_insert_purchases(records: list[dict]) -> int:
    """複数まとめて挿入。挿入件数を返す。"""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.executemany(
            """INSERT INTO purchases
               (email, name, nft_type, amount_jpy, units, team, transaction_id,
                purchased_at, status, returns_usdt, notes, imported_at, source_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    r.get("email", "").strip().lower(),
                    r.get("name", ""),
                    r.get("nft_type", ""),
                    r.get("amount_jpy"),
                    r.get("units"),
                    r.get("team", ""),
                    r.get("transaction_id", ""),
                    r.get("purchased_at", ""),
                    r.get("status", ""),
                    r.get("returns_usdt"),
                    r.get("notes", ""),
                    r.get("imported_at", now),
                    r.get("source_file", ""),
                )
                for r in records
            ],
        )
        return cur.rowcount


def get_purchases_by_email(email: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM purchases WHERE email = ? ORDER BY purchased_at ASC",
            (email.strip().lower(),),
        ).fetchall()
        return [dict(r) for r in rows]


def get_purchase_summary(email: str) -> dict:
    """指定メールの購入集計を返す（AI コンテキスト用）。"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT nft_type,
                      SUM(amount_jpy) AS total_jpy,
                      SUM(units) AS total_units,
                      SUM(returns_usdt) AS total_returns_usdt,
                      MIN(purchased_at) AS first_purchase,
                      COUNT(*) AS purchase_count
               FROM purchases WHERE email = ?
               GROUP BY nft_type
               ORDER BY first_purchase ASC""",
            (email.strip().lower(),),
        ).fetchall()
    return {
        "email": email,
        "by_nft": [dict(r) for r in rows],
        "total_count": sum(r["purchase_count"] for r in rows),
        "total_jpy": sum((r["total_jpy"] or 0) for r in rows),
        "total_returns_usdt": sum((r["total_returns_usdt"] or 0) for r in rows),
    }


def clear_purchases(source_file: Optional[str] = None) -> int:
    """購入レコードを削除（再インポート用）。source_file 指定時はそのファイル分のみ。"""
    with get_conn() as conn:
        if source_file:
            cur = conn.execute("DELETE FROM purchases WHERE source_file = ?", (source_file,))
        else:
            cur = conn.execute("DELETE FROM purchases")
        return cur.rowcount


def count_purchases() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM purchases").fetchone()["c"]


def distinct_emails_in_purchases() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(DISTINCT email) AS c FROM purchases").fetchone()["c"]
