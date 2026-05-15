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
AI_CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.75"))
AI_HISTORY_DEPTH = int(os.getenv("AI_HISTORY_DEPTH", "5"))
# True にすると AI の判断によらず必ず人手承認（Telegram）に回す
ALWAYS_HUMAN_APPROVAL = os.getenv("ALWAYS_HUMAN_APPROVAL", "true").lower() == "true"
PUBLIC_CHECK_EXPOSE_DETAILS = os.getenv("PUBLIC_CHECK_EXPOSE_DETAILS", "false").lower() == "true"
# /api/public/check の応答にメンバー名を含めるか（デフォルト true: 本人確認のため）
# 列挙対策はレート制限(ratelimit.limit_public_check)で担保している。
PUBLIC_CHECK_EXPOSE_NAME = os.getenv("PUBLIC_CHECK_EXPOSE_NAME", "true").lower() == "true"
# /api/public/check の応答に保有NFT種別を含めるか（デフォルト false: 投資規模漏洩防止）
PUBLIC_CHECK_EXPOSE_NFT_TYPES = os.getenv("PUBLIC_CHECK_EXPOSE_NFT_TYPES", "false").lower() == "true"
AI_KNOWLEDGE_PATH = os.getenv(
    "AI_KNOWLEDGE_PATH",
    os.path.join(os.path.dirname(__file__), "ai_knowledge.md"),
)

# ── テストセーフモード ──────────────────────────────────
# True のとき、TEST_ALLOWED_RECIPIENTS に列挙したアドレス以外への
# 実メール送信を完全にブロックする。本番運用時は false に。
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
_raw_test_recipients = os.getenv("TEST_ALLOWED_RECIPIENTS", "")
TEST_ALLOWED_RECIPIENTS: list[str] = [
    e.strip().lower() for e in _raw_test_recipients.split(",") if e.strip()
]

# ── Auth ────────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# ── CORS ─────────────────────────────────────────────
# カンマ区切りで複数指定可。"*" を含めると全許可（本番では非推奨）。
_raw_cors = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS: list[str] = [o.strip() for o in _raw_cors.split(",") if o.strip()]
# Vercel preview などワイルドカード正規表現で許可。空文字は無視。
_raw_cors_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip()
# 旧設定値 "https://.*.vercel.app" は意図せぬマッチを含むため、安全な正規表現に補正
if _raw_cors_regex == "https://.*.vercel.app":
    CORS_ORIGIN_REGEX: str = r"^https://([a-zA-Z0-9-]+\.)*vercel\.app$"
else:
    CORS_ORIGIN_REGEX = _raw_cors_regex

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
