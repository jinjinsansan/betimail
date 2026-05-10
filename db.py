import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sent_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_email TEXT NOT NULL,
                recipient_name TEXT,
                nft_type TEXT,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                sent_at TEXT NOT NULL
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
                ai_confidence REAL
            );

            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_email_id INTEGER NOT NULL,
                telegram_message_id INTEGER,
                ai_draft TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'waiting',
                FOREIGN KEY (received_email_id) REFERENCES received_emails(id)
            );
        """)


def record_sent_email(recipient_email: str, recipient_name: str, nft_type: str,
                       subject: str, body: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sent_emails (recipient_email, recipient_name, nft_type, subject, body, sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (recipient_email, recipient_name, nft_type, subject, body, datetime.now().isoformat())
        )
        return cur.lastrowid


def record_received_email(sender_email: str, sender_name: str, subject: str,
                           body: str, ai_draft: str = None, ai_confidence: float = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO received_emails (sender_email, sender_name, subject, body, received_at, ai_draft, ai_confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sender_email, sender_name, subject, body, datetime.now().isoformat(), ai_draft, ai_confidence)
        )
        return cur.lastrowid


def create_pending_approval(received_email_id: int, ai_draft: str, telegram_message_id: int = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pending_approvals (received_email_id, telegram_message_id, ai_draft, created_at) "
            "VALUES (?, ?, ?, ?)",
            (received_email_id, telegram_message_id, ai_draft, datetime.now().isoformat())
        )
        return cur.lastrowid


def get_pending_approval(approval_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT pa.*, re.sender_email, re.sender_name, re.subject as original_subject "
            "FROM pending_approvals pa "
            "JOIN received_emails re ON pa.received_email_id = re.id "
            "WHERE pa.id = ?", (approval_id,)
        ).fetchone()
        return dict(row) if row else None


def update_approval_status(approval_id: int, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE pending_approvals SET status = ? WHERE id = ?", (status, approval_id))
        conn.execute(
            "UPDATE received_emails SET status = ? "
            "WHERE id = (SELECT received_email_id FROM pending_approvals WHERE id = ?)",
            (status, approval_id)
        )


def get_sent_emails(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sent_emails ORDER BY sent_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_received_emails(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM received_emails ORDER BY received_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
