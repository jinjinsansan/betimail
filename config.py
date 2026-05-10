import os
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "")
RESEND_FROM_NAME = os.getenv("RESEND_FROM_NAME", "コミュニティサポート")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

AI_CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.7"))

RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET", "")

NFT_TYPES = [
    "会員権NFT",
    "パチスロホイホイNFT",
    "ラッキーマスタードNFT",
    "スペシャルマスタードNFT",
]

MEMBERS_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "members.csv")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "betimail.db")
