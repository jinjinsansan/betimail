import os
from dotenv import load_dotenv

load_dotenv()

# ── Resend ──────────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "")
RESEND_FROM_NAME = os.getenv("RESEND_FROM_NAME", "コミュニティサポート")
RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET", "")
_resend_from_domain = RESEND_FROM_EMAIL.rsplit("@", 1)[1].lower() if "@" in RESEND_FROM_EMAIL else ""
_raw_inbound_domains = os.getenv("RESEND_INBOUND_DOMAINS", _resend_from_domain)
RESEND_INBOUND_DOMAINS: list[str] = [
    d.strip().lower().lstrip("@") for d in _raw_inbound_domains.split(",") if d.strip()
]

# ── DeepSeek (OpenAI互換) ─────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

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
# /api/public/check の応答にメンバー名を含めるか（デフォルト false: 列挙リスク低減）
PUBLIC_CHECK_EXPOSE_NAME = os.getenv("PUBLIC_CHECK_EXPOSE_NAME", "false").lower() == "true"
# /api/public/check の応答に保有NFT種別を含めるか（デフォルト false: 投資規模漏洩防止）
PUBLIC_CHECK_EXPOSE_NFT_TYPES = os.getenv("PUBLIC_CHECK_EXPOSE_NFT_TYPES", "false").lower() == "true"
PUBLIC_CHECK_REQUIRE_OTP = os.getenv("PUBLIC_CHECK_REQUIRE_OTP", "false").lower() == "true"
PUBLIC_CHECK_OTP_TTL_SECONDS = int(os.getenv("PUBLIC_CHECK_OTP_TTL_SECONDS", "600"))
PUBLIC_CHECK_OTP_RESEND_SECONDS = int(os.getenv("PUBLIC_CHECK_OTP_RESEND_SECONDS", "60"))

# ラッキーマスタード会員ポータル(/lucky)のアクセス制限。
# 空     = 全会員に公開。
# 非空   = カンマ区切りで列挙したアドレスのみログイン可（ソフトローンチ・管理者限定公開用）。
_raw_lucky_allowed = os.getenv("LUCKY_PORTAL_ALLOWED_EMAILS", "")
LUCKY_PORTAL_ALLOWED_EMAILS: set[str] = {
    e.strip().lower() for e in _raw_lucky_allowed.split(",") if e.strip()
}

# ポータル(/portal betiダッシュボード再構築)のアクセス制限。lucky と同方式。
_raw_portal_allowed = os.getenv("PORTAL_ALLOWED_EMAILS", "")
PORTAL_ALLOWED_EMAILS: set[str] = {
    e.strip().lower() for e in _raw_portal_allowed.split(",") if e.strip()
}

# 白のダッシュボード(/white afi.irah.uk再構築)のアクセス制限。lucky と同方式。
_raw_white_allowed = os.getenv("WHITE_ALLOWED_EMAILS", "")
WHITE_ALLOWED_EMAILS: set[str] = {
    e.strip().lower() for e in _raw_white_allowed.split(",") if e.strip()
}

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
