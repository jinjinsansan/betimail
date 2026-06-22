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
    webhook_email_id TEXT,
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
    finished_at TEXT,
    scheduled_at TEXT,
    segment TEXT,
    confirm_all INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bulk_job_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    recipient_email TEXT NOT NULL,
    recipient_name TEXT,
    nft_type TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES bulk_send_jobs(id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS withdraw_requests (
    -- 出金申請（買い取り資金支払い等）。source で取得元を区別する。
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id INTEGER UNIQUE,          -- 取得元の出金申請レコード id（source 毎に名前空間を分けるため AFI は offset 付与）
    source TEXT DEFAULT 'nftportal',     -- 取得元: 'nftportal' | 'afi'
    email TEXT NOT NULL,
    name TEXT,
    user_id INTEGER,                     -- 取得元の user_id
    amount_usdt REAL NOT NULL,           -- 支払額 (USDT)
    destination TEXT,                    -- 送金先ウォレットアドレス
    type INTEGER,
    status INTEGER,                      -- 取得元 status。nftportal: 2=完了 / afi: status_request 1=未承認,2=承認済
    requested_at TEXT,                   -- created_at (申請日時)
    action_at TEXT,                      -- 処理日時
    secret_code TEXT,
    packet TEXT,
    title TEXT,
    nft_kind TEXT DEFAULT '会員権NFT',    -- 対象 NFT 種別
    raw_json TEXT,                       -- 元レコード保管
    imported_at TEXT NOT NULL,
    notified_at TEXT                     -- Telegram 通知済みのフラグ
);

CREATE INDEX IF NOT EXISTS idx_sent_recipient ON sent_emails(recipient_email);
CREATE INDEX IF NOT EXISTS idx_recv_sender ON received_emails(sender_email);
CREATE INDEX IF NOT EXISTS idx_recv_status ON received_emails(status);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON pending_approvals(status);
CREATE INDEX IF NOT EXISTS idx_purchases_email ON purchases(email);
CREATE INDEX IF NOT EXISTS idx_purchases_nft ON purchases(nft_type);
CREATE INDEX IF NOT EXISTS idx_withdraws_email ON withdraw_requests(email);
CREATE INDEX IF NOT EXISTS idx_withdraws_external ON withdraw_requests(external_id);
CREATE INDEX IF NOT EXISTS idx_bulk_targets_job_id ON bulk_job_targets(job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bulk_targets_job_email_unique
    ON bulk_job_targets(job_id, recipient_email);

-- ── ラッキーマスタード会員ポータル ──────────────────────
-- 元サイト luckymustard.uk (恒久ダウン) の代替。会員は LUCKY_MUSTARD のみ閲覧。
-- 報酬式: 入金額 = 保有NFT枚数 × (日次プール ÷ 総NFT枚数)
CREATE TABLE IF NOT EXISTS lucky_members (
    email TEXT PRIMARY KEY,             -- 小文字正規化したメール（ログインキー）
    name TEXT,
    lucky_user_id INTEGER,             -- 元 DB の users.id
    nft_count INTEGER DEFAULT 0,       -- 報酬対象(ステーク)NFT枚数。日次報酬の按分基準
    owned_nft INTEGER DEFAULT 0,       -- 累計購入枚数 (buy_nft 由来・参考値)
    balance REAL DEFAULT 0,            -- 現在残高 (USDT)
    cumulative_reward REAL DEFAULT 0,  -- 累計報酬 (USDT)
    last_reward_at TEXT,
    source TEXT DEFAULT 'dump',        -- 'dump'(移行) | 'manual'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lucky_distributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id INTEGER UNIQUE,        -- 元 reward_distribution_histories.id（移行分の重複防止）。新規は NULL
    nft TEXT DEFAULT 'LUCKY_MUSTARD',
    distributed_for TEXT,             -- 対象日時 (JST, 元サイトの time 相当)
    pool_amount REAL NOT NULL,        -- その回の総分配額 (USDT)
    total_nft INTEGER NOT NULL,       -- 分配時の総 NFT 枚数
    rate REAL,                        -- pool_amount / total_nft (1枚あたり)
    recipients INTEGER DEFAULT 0,     -- 受取人数
    status TEXT DEFAULT 'done',
    created_by TEXT DEFAULT 'migration',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lucky_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id INTEGER UNIQUE,        -- 元 balance_change_history.id（移行分の重複防止）。新規は NULL
    distribution_id INTEGER,          -- lucky_distributions.id（新規分配時に紐付け）
    email TEXT NOT NULL,
    nft_count INTEGER,                -- そのとき報酬対象だった枚数
    amount REAL NOT NULL,             -- 入金額 (USDT)
    balance_after REAL,               -- 取引後残高
    rewarded_at TEXT,                 -- 日時 (JST ISO)
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lucky_rewards_email ON lucky_rewards(email);
CREATE INDEX IF NOT EXISTS idx_lucky_rewards_dist ON lucky_rewards(distribution_id);
CREATE INDEX IF NOT EXISTS idx_lucky_rewards_at ON lucky_rewards(rewarded_at);
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
        _ensure_column(conn, "received_emails", "webhook_email_id", "webhook_email_id TEXT")
        _ensure_column(conn, "received_emails", "in_reply_to", "in_reply_to TEXT")
        _ensure_column(conn, "pending_approvals", "handled_at", "handled_at TEXT")
        _ensure_column(conn, "pending_approvals", "handled_by", "handled_by TEXT")
        _ensure_column(conn, "bulk_send_jobs", "scheduled_at", "scheduled_at TEXT")
        _ensure_column(conn, "bulk_send_jobs", "segment", "segment TEXT")
        _ensure_column(conn, "bulk_send_jobs", "confirm_all", "confirm_all INTEGER DEFAULT 0")
        # 出金申請の取得元（既存行は nftportal 由来）
        _ensure_column(conn, "withdraw_requests", "source", "source TEXT DEFAULT 'nftportal'")
        # ラッキー会員: 累計購入枚数（参考値）
        _ensure_column(conn, "lucky_members", "owned_nft", "owned_nft INTEGER DEFAULT 0")
        try:
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_recv_message_id_unique
                   ON received_emails(message_id)
                   WHERE message_id IS NOT NULL AND message_id <> ''"""
            )
        except sqlite3.IntegrityError:
            log.warning("Skipping unique index idx_recv_message_id_unique due to existing duplicates")
        try:
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_recv_webhook_email_id_unique
                   ON received_emails(webhook_email_id)
                   WHERE webhook_email_id IS NOT NULL AND webhook_email_id <> ''"""
            )
        except sqlite3.IntegrityError:
            log.warning("Skipping unique index idx_recv_webhook_email_id_unique due to existing duplicates")
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
    webhook_email_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> int:
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO received_emails
                   (sender_email, sender_name, subject, body, received_at,
                    ai_draft, ai_confidence, message_id, webhook_email_id, in_reply_to)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sender_email, sender_name, subject, body, datetime.now().isoformat(),
                 ai_draft, ai_confidence, message_id, webhook_email_id, in_reply_to),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            if message_id:
                row = conn.execute(
                    "SELECT id FROM received_emails WHERE message_id = ?",
                    (message_id,),
                ).fetchone()
                if row:
                    return row["id"]
            if webhook_email_id:
                row = conn.execute(
                    "SELECT id FROM received_emails WHERE webhook_email_id = ?",
                    (webhook_email_id,),
                ).fetchone()
                if row:
                    return row["id"]
            raise


def record_received_email_if_new(
    sender_email: str,
    sender_name: str,
    subject: str,
    body: str,
    ai_draft: Optional[str] = None,
    ai_confidence: Optional[float] = None,
    message_id: Optional[str] = None,
    webhook_email_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> tuple[int, bool]:
    """受信メールを記録。message_id/webhook_email_id 重複時は既存 id を返し、新規作成フラグを False にする。"""
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO received_emails
                   (sender_email, sender_name, subject, body, received_at,
                    ai_draft, ai_confidence, message_id, webhook_email_id, in_reply_to)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sender_email, sender_name, subject, body, datetime.now().isoformat(),
                 ai_draft, ai_confidence, message_id, webhook_email_id, in_reply_to),
            )
            return cur.lastrowid, True
        except sqlite3.IntegrityError:
            if message_id:
                row = conn.execute(
                    "SELECT id FROM received_emails WHERE message_id = ?",
                    (message_id,),
                ).fetchone()
                if row:
                    return row["id"], False
            if webhook_email_id:
                row = conn.execute(
                    "SELECT id FROM received_emails WHERE webhook_email_id = ?",
                    (webhook_email_id,),
                ).fetchone()
                if row:
                    return row["id"], False
            raise


def has_received_message_id(message_id: str) -> bool:
    if not message_id:
        return False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM received_emails WHERE message_id = ? LIMIT 1",
            (message_id,),
        ).fetchone()
        return row is not None


def has_received_webhook_email_id(webhook_email_id: str) -> bool:
    if not webhook_email_id:
        return False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM received_emails WHERE webhook_email_id = ? LIMIT 1",
            (webhook_email_id,),
        ).fetchone()
        return row is not None


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


def claim_pending_approval(approval_id: int, handled_by: str = "") -> bool:
    """status=waiting の承認のみを原子的に processing に遷移。成功時 True。"""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE pending_approvals
               SET status = 'processing', handled_at = ?, handled_by = ?
               WHERE id = ? AND status = 'waiting'""",
            (now, handled_by, approval_id),
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            """UPDATE received_emails SET status = 'processing'
               WHERE id = (SELECT received_email_id FROM pending_approvals WHERE id = ?)""",
            (approval_id,),
        )
        return True


def release_pending_approval(approval_id: int) -> None:
    """送信失敗時などに processing から waiting へ戻す。"""
    with get_conn() as conn:
        conn.execute(
            """UPDATE pending_approvals
               SET status = 'waiting', handled_at = NULL, handled_by = NULL
               WHERE id = ? AND status = 'processing'""",
            (approval_id,),
        )
        conn.execute(
            """UPDATE received_emails SET status = 'pending'
               WHERE id = (SELECT received_email_id FROM pending_approvals WHERE id = ?)""",
            (approval_id,),
        )


def update_approval_telegram_message(approval_id: int, telegram_message_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE pending_approvals SET telegram_message_id = ? WHERE id = ?",
            (telegram_message_id, approval_id),
        )


def update_approval_draft(approval_id: int, new_draft: str) -> None:
    """承認待ちの AI下書きを書き換える（Telegram での AI 相談モード時に使用）。"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE pending_approvals SET ai_draft = ? WHERE id = ?",
            (new_draft, approval_id),
        )


# ── 履歴 ────────────────────────────────────────────────
def get_sent_emails(
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    bulk: str = "exclude",
) -> list[dict]:
    """
    bulk:
      "exclude" - bulk_job_id IS NULL のみ（個別メールのみ・既定）
      "only"    - bulk_job_id IS NOT NULL のみ（メルマガのみ）
      "include" - フィルタなし
    """
    where: list[str] = []
    args: list = []
    if search:
        where.append("(recipient_email LIKE ? OR recipient_name LIKE ? OR subject LIKE ?)")
        like = f"%{search}%"
        args += [like, like, like]
    if bulk == "exclude":
        where.append("bulk_job_id IS NULL")
    elif bulk == "only":
        where.append("bulk_job_id IS NOT NULL")
    q = "SELECT * FROM sent_emails"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY sent_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with get_conn() as conn:
        rows = conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]


def count_sent_emails(search: str = "", bulk: str = "exclude") -> int:
    where: list[str] = []
    args: list = []
    if search:
        where.append("(recipient_email LIKE ? OR recipient_name LIKE ? OR subject LIKE ?)")
        like = f"%{search}%"
        args += [like, like, like]
    if bulk == "exclude":
        where.append("bulk_job_id IS NULL")
    elif bulk == "only":
        where.append("bulk_job_id IS NOT NULL")
    q = "SELECT COUNT(*) as c FROM sent_emails"
    if where:
        q += " WHERE " + " AND ".join(where)
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
def create_bulk_job(
    subject: str,
    body: str,
    nft_types: str,
    total: int,
    *,
    scheduled_at: Optional[str] = None,
    segment: Optional[str] = None,
    confirm_all: bool = False,
    recipients: Optional[list[dict]] = None,
) -> int:
    """通常ジョブ (scheduled_at=None) は 'running'、予約ジョブは 'scheduled' で作成。

    scheduled_at は UTC ISO8601 文字列 (例: "2026-05-16T11:30:00+00:00")。
    """
    status = "scheduled" if scheduled_at else "running"
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO bulk_send_jobs
               (subject, body, nft_types, total, status, created_at, scheduled_at, segment, confirm_all)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                subject, body, nft_types, total, status,
                datetime.now().isoformat(),
                scheduled_at, segment, 1 if confirm_all else 0,
            ),
        )
        job_id = cur.lastrowid
        if recipients:
            conn.executemany(
                """INSERT OR IGNORE INTO bulk_job_targets
                   (job_id, recipient_email, recipient_name, nft_type, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        job_id,
                        (r.get("email") or "").strip().lower(),
                        r.get("name", ""),
                        r.get("nft_type", ""),
                        datetime.now().isoformat(),
                    )
                    for r in recipients
                    if (r.get("email") or "").strip()
                ],
            )
        return job_id


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


def cancel_scheduled_job(job_id: int) -> bool:
    """予約ジョブをキャンセル。status='scheduled' の時のみ成功。"""
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE bulk_send_jobs
               SET status = 'cancelled', finished_at = ?
               WHERE id = ? AND status = 'scheduled'""",
            (datetime.now().isoformat(), job_id),
        )
        return cur.rowcount > 0


def get_bulk_job_targets(job_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT recipient_email as email, recipient_name as name, nft_type
               FROM bulk_job_targets
               WHERE job_id = ?
               ORDER BY id ASC""",
            (job_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def claim_due_scheduled_jobs(now_utc_iso: str) -> list[dict]:
    """期限到達した予約ジョブを atomic に取得し、status='running' に遷移させる。

    cron が並列実行されても、UPDATE ... WHERE status='scheduled' の row-level
    write lock で重複処理は起きない (SQLite は write は直列化される)。
    """
    with get_conn() as conn:
        cur = conn.execute(
            """SELECT * FROM bulk_send_jobs
               WHERE status = 'scheduled' AND scheduled_at <= ?
               ORDER BY scheduled_at ASC""",
            (now_utc_iso,),
        )
        candidates = [dict(r) for r in cur.fetchall()]
        claimed = []
        for j in candidates:
            cur = conn.execute(
                """UPDATE bulk_send_jobs SET status = 'running'
                   WHERE id = ? AND status = 'scheduled'""",
                (j["id"],),
            )
            if cur.rowcount > 0:
                j["status"] = "running"
                claimed.append(j)
        return claimed


def fail_bulk_job(job_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE bulk_send_jobs SET status = 'error', finished_at = ? WHERE id = ?",
            (datetime.now().isoformat(), job_id),
        )


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


# ── 出金申請 (買い取り資金) ──────────────────────────────
def upsert_withdraw(record: dict) -> bool:
    """external_id が既存なら更新、なければ挿入。新規 (=新着) なら True を返す。"""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM withdraw_requests WHERE external_id = ?",
            (record["external_id"],),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE withdraw_requests
                   SET source=?, email=?, name=?, user_id=?, amount_usdt=?, destination=?,
                       type=?, status=?, requested_at=?, action_at=?, secret_code=?,
                       packet=?, title=?, nft_kind=?, raw_json=?
                   WHERE id=?""",
                (
                    record.get("source", "nftportal"),
                    record.get("email", "").strip().lower(),
                    record.get("name"),
                    record.get("user_id"),
                    record.get("amount_usdt"),
                    record.get("destination"),
                    record.get("type"),
                    record.get("status"),
                    record.get("requested_at"),
                    record.get("action_at"),
                    record.get("secret_code"),
                    record.get("packet"),
                    record.get("title"),
                    record.get("nft_kind", "会員権NFT"),
                    record.get("raw_json"),
                    existing["id"],
                ),
            )
            return False
        conn.execute(
            """INSERT INTO withdraw_requests
               (external_id, source, email, name, user_id, amount_usdt, destination, type, status,
                requested_at, action_at, secret_code, packet, title, nft_kind, raw_json, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["external_id"],
                record.get("source", "nftportal"),
                record.get("email", "").strip().lower(),
                record.get("name"),
                record.get("user_id"),
                record.get("amount_usdt"),
                record.get("destination"),
                record.get("type"),
                record.get("status"),
                record.get("requested_at"),
                record.get("action_at"),
                record.get("secret_code"),
                record.get("packet"),
                record.get("title"),
                record.get("nft_kind", "会員権NFT"),
                record.get("raw_json"),
                now,
            ),
        )
        return True


def list_withdraws(
    limit: int = 200,
    email: Optional[str] = None,
    source: Optional[str] = None,
) -> list[dict]:
    q = "SELECT * FROM withdraw_requests"
    conds: list[str] = []
    args: list = []
    if email:
        conds.append("email = ?")
        args.append(email.strip().lower())
    if source:
        conds.append("source = ?")
        args.append(source)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY requested_at DESC LIMIT ?"
    args.append(limit)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def get_withdraw_summary_by_email(email: str) -> dict:
    """指定 email の買い取り資金支払い集計。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM withdraw_requests WHERE email = ? ORDER BY requested_at ASC",
            (email.strip().lower(),),
        ).fetchall()
    total = sum((r["amount_usdt"] or 0) for r in rows)
    return {
        "email": email,
        "count": len(rows),
        "total_usdt": total,
        "withdraws": [dict(r) for r in rows],
    }


def mark_withdraw_notified(external_id: int) -> None:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE withdraw_requests SET notified_at = ? WHERE external_id = ?",
            (now, external_id),
        )


def unnotified_withdraws() -> list[dict]:
    """まだ Telegram 通知してない withdraw レコード。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM withdraw_requests WHERE notified_at IS NULL ORDER BY requested_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


# ── ラッキーマスタード会員ポータル ──────────────────────
def bulk_upsert_lucky_members(members: list[dict]) -> int:
    """会員を一括 upsert（email キー）。移行・再集計用。件数を返す。"""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.executemany(
            """INSERT INTO lucky_members
               (email, name, lucky_user_id, nft_count, owned_nft, balance, cumulative_reward,
                last_reward_at, source, created_at, updated_at)
               VALUES (:email, :name, :lucky_user_id, :nft_count, :owned_nft, :balance,
                       :cumulative_reward, :last_reward_at, :source, :created_at, :updated_at)
               ON CONFLICT(email) DO UPDATE SET
                   name=excluded.name,
                   lucky_user_id=excluded.lucky_user_id,
                   nft_count=excluded.nft_count,
                   owned_nft=excluded.owned_nft,
                   balance=excluded.balance,
                   cumulative_reward=excluded.cumulative_reward,
                   last_reward_at=excluded.last_reward_at,
                   source=excluded.source,
                   updated_at=excluded.updated_at""",
            [
                {
                    "email": (m.get("email") or "").strip().lower(),
                    "name": m.get("name", ""),
                    "lucky_user_id": m.get("lucky_user_id"),
                    "nft_count": m.get("nft_count", 0),
                    "owned_nft": m.get("owned_nft", 0),
                    "balance": m.get("balance", 0),
                    "cumulative_reward": m.get("cumulative_reward", 0),
                    "last_reward_at": m.get("last_reward_at"),
                    "source": m.get("source", "dump"),
                    "created_at": m.get("created_at", now),
                    "updated_at": now,
                }
                for m in members
                if (m.get("email") or "").strip()
            ],
        )
        return cur.rowcount


def bulk_insert_lucky_distributions(rows: list[dict]) -> int:
    """分配イベントを一括挿入（external_id で重複防止）。挿入件数を返す。"""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.executemany(
            """INSERT OR IGNORE INTO lucky_distributions
               (external_id, nft, distributed_for, pool_amount, total_nft, rate,
                recipients, status, created_by, created_at)
               VALUES (:external_id, :nft, :distributed_for, :pool_amount, :total_nft,
                       :rate, :recipients, :status, :created_by, :created_at)""",
            [
                {
                    "external_id": r.get("external_id"),
                    "nft": r.get("nft", "LUCKY_MUSTARD"),
                    "distributed_for": r.get("distributed_for"),
                    "pool_amount": r.get("pool_amount", 0),
                    "total_nft": r.get("total_nft", 0),
                    "rate": r.get("rate"),
                    "recipients": r.get("recipients", 0),
                    "status": r.get("status", "done"),
                    "created_by": r.get("created_by", "migration"),
                    "created_at": r.get("created_at", now),
                }
                for r in rows
            ],
        )
        return cur.rowcount


def bulk_insert_lucky_rewards(rows: list[dict], batch: int = 5000) -> int:
    """報酬明細を一括挿入（external_id で重複防止）。挿入件数を返す。"""
    now = datetime.now().isoformat()
    inserted = 0
    with get_conn() as conn:
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            cur = conn.executemany(
                """INSERT OR IGNORE INTO lucky_rewards
                   (external_id, distribution_id, email, nft_count, amount,
                    balance_after, rewarded_at, created_at)
                   VALUES (:external_id, :distribution_id, :email, :nft_count, :amount,
                           :balance_after, :rewarded_at, :created_at)""",
                [
                    {
                        "external_id": r.get("external_id"),
                        "distribution_id": r.get("distribution_id"),
                        "email": (r.get("email") or "").strip().lower(),
                        "nft_count": r.get("nft_count"),
                        "amount": r.get("amount", 0),
                        "balance_after": r.get("balance_after"),
                        "rewarded_at": r.get("rewarded_at"),
                        "created_at": r.get("created_at", now),
                    }
                    for r in chunk
                    if (r.get("email") or "").strip()
                ],
            )
            inserted += cur.rowcount
    return inserted


def get_lucky_member(email: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM lucky_members WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        return dict(row) if row else None


def get_lucky_rewards(email: str, limit: int = 400) -> list[dict]:
    """会員の報酬明細を新しい順に返す（履歴・グラフ用）。"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT amount, nft_count, balance_after, rewarded_at
               FROM lucky_rewards WHERE email = ?
               ORDER BY rewarded_at DESC, id DESC LIMIT ?""",
            (email.strip().lower(), limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_lucky_distribution() -> Optional[dict]:
    """最新の分配イベント（現在の単価・総NFT枚数の参照用）。"""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM lucky_distributions
               ORDER BY distributed_for DESC, id DESC LIMIT 1"""
        ).fetchone()
        return dict(row) if row else None


def list_lucky_distributions(limit: int = 60) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM lucky_distributions ORDER BY distributed_for DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def lucky_totals() -> dict:
    """会員全体の集計（管理画面ダッシュボード用）。"""
    with get_conn() as conn:
        r = conn.execute(
            """SELECT COUNT(*) AS members,
                      COALESCE(SUM(nft_count), 0) AS total_nft,
                      COALESCE(SUM(balance), 0) AS total_balance,
                      COALESCE(SUM(cumulative_reward), 0) AS total_reward
               FROM lucky_members
               WHERE nft_count > 0 AND COALESCE(source, '') != 'preview'"""
        ).fetchone()
        return dict(r)


def clear_lucky_tables() -> None:
    """移行のやり直し用（lucky_* を全消去）。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM lucky_rewards")
        conn.execute("DELETE FROM lucky_distributions")
        conn.execute("DELETE FROM lucky_members")


def get_lucky_dashboard(email: str) -> Optional[dict]:
    """会員ポータル用のダッシュボードデータ（タイル＋報酬推移＋履歴）。"""
    member = get_lucky_member(email)
    if not member:
        return None
    rewards = get_lucky_rewards(email, limit=400)  # 新しい順
    latest = get_latest_lucky_distribution()
    rate = (latest or {}).get("rate") or 0.0
    nft = member.get("nft_count") or 0
    today_reward = round(nft * rate, 2)
    # グラフ用に古い順の系列（残高の推移＝報酬の積み上がり）
    series = [
        {
            "date": (r["rewarded_at"] or "")[:10],
            "amount": r["amount"],
            "balance_after": r["balance_after"],
        }
        for r in reversed(rewards)
    ]
    return {
        "email": member["email"],
        "name": member.get("name"),
        "nft_count": nft,
        "owned_nft": member.get("owned_nft") or 0,
        "balance": member.get("balance") or 0,
        "cumulative_reward": member.get("cumulative_reward") or 0,
        "today_reward": today_reward,
        "rate": rate,
        "last_reward_at": member.get("last_reward_at"),
        "history": rewards[:120],
        "series": series,
    }


def create_lucky_distribution(
    pool_amount: float,
    *,
    created_by: str = "admin",
    distributed_for: Optional[str] = None,
    nft: str = "LUCKY_MUSTARD",
) -> dict:
    """日次報酬分配を DB 内でアトミックに実行する。

    各会員へ amount = round(nft_count × pool_amount / total_nft, 2) を加算し、
    lucky_distributions（1行）と lucky_rewards（会員ごと）を記録、lucky_members の
    balance / cumulative_reward / last_reward_at を更新する。
    """
    now = datetime.now().isoformat()
    distributed_for = distributed_for or now
    with get_conn() as conn:
        members = conn.execute(
            """SELECT email, nft_count, balance, cumulative_reward FROM lucky_members
               WHERE nft_count > 0 AND COALESCE(source, '') != 'preview'"""
        ).fetchall()
        total_nft = sum((m["nft_count"] or 0) for m in members)
        if total_nft <= 0:
            raise ValueError("報酬対象 NFT が 0 のため分配できません")
        rate = pool_amount / total_nft
        cur = conn.execute(
            """INSERT INTO lucky_distributions
               (external_id, nft, distributed_for, pool_amount, total_nft, rate,
                recipients, status, created_by, created_at)
               VALUES (NULL, ?, ?, ?, ?, ?, ?, 'done', ?, ?)""",
            (nft, distributed_for, pool_amount, total_nft, rate, len(members), created_by, now),
        )
        dist_id = cur.lastrowid
        reward_params = []
        member_updates = []
        distributed_total = 0.0
        for m in members:
            cnt = m["nft_count"] or 0
            amt = round(cnt * rate, 2)
            new_bal = round((m["balance"] or 0) + amt, 2)
            new_cum = round((m["cumulative_reward"] or 0) + amt, 2)
            distributed_total += amt
            reward_params.append((dist_id, m["email"], cnt, amt, new_bal, distributed_for, now))
            member_updates.append((new_bal, new_cum, distributed_for, m["email"]))
        conn.executemany(
            """INSERT INTO lucky_rewards
               (external_id, distribution_id, email, nft_count, amount, balance_after, rewarded_at, created_at)
               VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)""",
            reward_params,
        )
        conn.executemany(
            """UPDATE lucky_members
               SET balance = ?, cumulative_reward = ?, last_reward_at = ?, updated_at = ?
               WHERE email = ?""",
            [(b, c, lr, now, e) for (b, c, lr, e) in member_updates],
        )
        return {
            "distribution_id": dist_id,
            "nft": nft,
            "recipients": len(members),
            "total_nft": total_nft,
            "pool_amount": pool_amount,
            "rate": rate,
            "distributed_total": round(distributed_total, 2),
            "distributed_for": distributed_for,
        }


def lucky_distribution_exists_for_date(date_str: str, nft: str = "LUCKY_MUSTARD") -> bool:
    """指定日(YYYY-MM-DD)の分配が既にあるか（二重分配防止・backfill用）。"""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT 1 FROM lucky_distributions
               WHERE nft = ? AND substr(distributed_for, 1, 10) = ? LIMIT 1""",
            (nft, date_str),
        ).fetchone()
        return row is not None
