"""ラッキーマスタード会員ポータルのテスト。"""
from fastapi.testclient import TestClient


def _seed_member(db, email="taro@example.com", name="山田太郎", nft=2):
    db.bulk_upsert_lucky_members([{
        "email": email, "name": name, "lucky_user_id": 1,
        "nft_count": nft, "owned_nft": nft, "balance": 100.0,
        "cumulative_reward": 50.0, "source": "test",
    }])
    return email


def test_distribution_credits_proportionally():
    import db
    _seed_member(db, "a@example.com", "A", nft=3)
    _seed_member(db, "b@example.com", "B", nft=1)
    res = db.create_lucky_distribution(400.0, created_by="test")
    assert res["total_nft"] == 4
    assert res["recipients"] == 2
    # rate = 100/枚
    a = db.get_lucky_member("a@example.com")
    b = db.get_lucky_member("b@example.com")
    assert a["balance"] == 400.0   # 100 + 3*100
    assert b["balance"] == 200.0   # 100 + 1*100
    assert a["cumulative_reward"] == 350.0  # 50 + 300


def test_distribution_blocks_when_no_nft():
    import db
    import pytest
    with pytest.raises(ValueError):
        db.create_lucky_distribution(100.0)


def test_dashboard_shape():
    import db
    _seed_member(db, "c@example.com", "C", nft=2)
    db.create_lucky_distribution(200.0, created_by="test")  # rate 100/枚
    d = db.get_lucky_dashboard("c@example.com")
    assert d["nft_count"] == 2
    assert d["today_reward"] == 200.0   # 2 * 100
    assert d["balance"] == 300.0        # 100 + 2*100
    assert len(d["history"]) == 1
    assert d["history"][0]["amount"] == 200.0


def test_lucky_login_non_member_returns_found_false():
    import main
    client = TestClient(main.app)
    r = client.post("/api/lucky/login", json={"email": "nobody@nowhere.com"})
    assert r.status_code == 200
    assert r.json() == {"found": False}


def test_lucky_me_requires_token():
    import main
    client = TestClient(main.app)
    r = client.get("/api/lucky/me")
    assert r.status_code == 401


def test_lucky_me_with_member_token():
    import db, auth, main
    _seed_member(db, "d@example.com", "D", nft=2)
    db.create_lucky_distribution(200.0, created_by="test")
    tok = auth.issue_member_token("d@example.com")
    client = TestClient(main.app)
    r = client.get("/api/lucky/me", headers={"Authorization": f"Bearer {tok['token']}"})
    assert r.status_code == 200
    d = r.json()
    assert d["email"] == "d@example.com"
    assert d["nft_count"] == 2
    assert d["today_reward"] == 200.0


def test_lucky_distribute_requires_admin():
    import main
    client = TestClient(main.app)
    # ADMIN_PASSWORD 未設定(テスト環境)なので 503、設定時は 401
    r = client.post("/api/lucky/distribute", json={"amount": 352})
    assert r.status_code in (401, 503)
