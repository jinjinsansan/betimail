import os
from dotenv import load_dotenv

load_dotenv()

# ── Resend ──────────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "")
RESEND_FROM_NAME = os.getenv("RESEND_FROM_NAME", "コミュニティサポート")
RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET", "")

# ── Anthropic ───────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")

# ── Telegram (comma-separated chat_ids supported) ───────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_raw_chat_ids = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS: list[str] = [c.strip() for c in _raw_chat_ids.split(",") if c.strip()]

# ── AI behavior ─────────────────────────────────────────
AI_CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.7"))
AI_HISTORY_DEPTH = int(os.getenv("AI_HISTORY_DEPTH", "5"))

# ── Auth ────────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# ── Welcome email ───────────────────────────────────────
SEND_WELCOME_EMAIL = os.getenv("SEND_WELCOME_EMAIL", "true").lower() == "true"

# ── Logging ─────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Constants ───────────────────────────────────────────
NFT_TYPES = [
    "会員権NFT",
    "パチスロホイホイNFT",
    "ラッキーマスタードNFT",
    "スペシャルマスタードNFT",
]

MEMBERS_CSV_PATH = os.getenv(
    "BETIMAIL_MEMBERS_CSV_PATH",
    os.path.join(os.path.dirname(__file__), "data", "members.csv"),
)
DB_PATH = os.getenv(
    "BETIMAIL_DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "betimail.db"),
)
