"""テスト共通設定。各テストで一時ディレクトリの DB / CSV を使う。

ポイント: モジュールをリロードするテストがあるので、設定は環境変数経由で渡す。
"""
import os
import sys
import importlib
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def temp_data(monkeypatch, tmp_path):
    csv_path = tmp_path / "members.csv"
    db_path = tmp_path / "betimail.db"
    monkeypatch.setenv("BETIMAIL_MEMBERS_CSV_PATH", str(csv_path))
    monkeypatch.setenv("BETIMAIL_DB_PATH", str(db_path))
    monkeypatch.setenv("RESEND_API_KEY", "test")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "test@example.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("SEND_WELCOME_EMAIL", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "")

    # 既に読み込まれているモジュールをリロードして env を反映
    for mod_name in ("config", "members", "db", "auth", "webhook", "mail", "ai", "telegram_bot", "main"):
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])

    import db
    db.init_db()
    yield
