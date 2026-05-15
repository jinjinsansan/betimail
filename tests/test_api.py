"""主要 API のエンドポイント単体テスト。"""
from fastapi.testclient import TestClient
import importlib


def _fresh_client(monkeypatch, admin_password: str = "secret123"):
    """環境変数を確定させてから main をリロードして TestClient を返す。"""
    monkeypatch.setenv("ADMIN_PASSWORD", admin_password)
    import sys
    for mod in ("config", "members", "db", "auth", "ratelimit", "webhook", "mail", "ai", "telegram_bot", "main"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    import db
    import main
    db.init_db()
    return TestClient(main.app)


def _auth_headers(client: TestClient, password: str = "secret123") -> dict:
    r = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_endpoint(monkeypatch):
    client = _fresh_client(monkeypatch)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_add_and_list_members(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    r = client.post("/api/members", json={
        "name": "山田太郎", "email": "y@example.com",
        "nft_type": "会員権NFT", "joined_date": "2024-01-01",
    }, headers=headers)
    assert r.status_code == 200, r.text
    list_r = client.get("/api/members", headers=headers)
    assert list_r.status_code == 200
    assert len(list_r.json()) == 1


def test_invalid_email_rejected(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    r = client.post("/api/members", json={
        "name": "X", "email": "not-an-email",
        "nft_type": "会員権NFT", "joined_date": "2024-01-01",
    }, headers=headers)
    assert r.status_code == 422


def test_update_member_endpoint(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    client.post("/api/members", json={
        "name": "A", "email": "a@example.com",
        "nft_type": "会員権NFT", "joined_date": "2024-01-01",
    }, headers=headers)
    r = client.put("/api/members/a@example.com", json={"name": "B"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "B"


def test_preview_endpoint(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    r = client.post("/api/preview", json={"body": "Hello {name}", "sample": {"name": "太郎"}}, headers=headers)
    assert r.status_code == 200
    assert r.json()["rendered"] == "Hello 太郎"


def test_preview_unknown_placeholder(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    r = client.post("/api/preview", json={"body": "{unknown}"}, headers=headers)
    assert r.status_code == 400


def test_template_crud(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    r = client.post("/api/templates", json={"name": "n", "subject": "s", "body": "b"}, headers=headers)
    assert r.status_code == 200
    tid = r.json()["id"]
    assert client.get("/api/templates", headers=headers).json()[0]["name"] == "n"
    assert client.delete(f"/api/templates/{tid}", headers=headers).status_code == 200


def test_auth_required_when_password_set(monkeypatch):
    client = _fresh_client(monkeypatch, admin_password="secret123")

    # 認証なしは401
    r = client.get("/api/members")
    assert r.status_code == 401

    # ログインしてトークン取得
    r = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    # Bearer トークンで200
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/members", headers=headers)
    assert r.status_code == 200

    # 不正トークンは401
    r = client.get("/api/members", headers={"Authorization": "Bearer garbage.signature"})
    assert r.status_code == 401

    # 間違ったパスワードは401
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_when_not_configured(monkeypatch):
    client = _fresh_client(monkeypatch, admin_password="")
    r = client.post("/api/auth/login", json={"username": "admin", "password": "anything"})
    assert r.status_code == 503


def test_nft_types(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    r = client.get("/api/nft-types", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 4


def test_require_admin_returns_503_when_not_configured(monkeypatch):
    client = _fresh_client(monkeypatch, admin_password="")
    r = client.get("/api/members")
    assert r.status_code == 503


def test_public_check_hides_pii_by_default(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    client.post("/api/members", json={
        "name": "山田太郎", "email": "y@example.com",
        "nft_type": "会員権NFT, ラッキーマスタードNFT", "joined_date": "2024-01-01",
    }, headers=headers)
    r = client.post("/api/public/check", json={"email": "y@example.com"})
    assert r.status_code == 200
    payload = r.json()
    assert payload == {"found": True}


def test_send_requires_confirm_all(monkeypatch):
    client = _fresh_client(monkeypatch)
    headers = _auth_headers(client)
    client.post("/api/members", json={
        "name": "A", "email": "a@example.com",
        "nft_type": "会員権NFT", "joined_date": "2024-01-01",
    }, headers=headers)
    r = client.post("/api/send", json={"nft_types": [], "subject": "s", "body": "b"}, headers=headers)
    assert r.status_code == 400
