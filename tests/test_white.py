"""白のダッシュボード（afi.irah.uk 再構築）のテスト。"""
from fastapi.testclient import TestClient


def _seed_member(db, email="taro@example.com", name="山田太郎", *,
                 balance=100.0, kaiin=4, hoihoi=2, source="scrape"):
    db.bulk_upsert_afi_members([{
        "email": email, "name": name, "afi_user_id": 1,
        "wallet_address": None, "balance": balance,
        "kaiin_units": kaiin, "hoihoi_units": hoihoi,
        "source": source, "snapshot_at": "2026-07-20T12:00:00",
    }])
    return email


def test_dashboard_shape():
    import db
    _seed_member(db, "d@example.com", "D", balance=55.5, kaiin=4, hoihoi=2)
    d = db.get_afi_dashboard("d@example.com")
    assert d["balance"] == 55.5
    assert d["kaiin_units"] == 4
    assert d["hoihoi_units"] == 2
    assert d["withdrawals"] == []
    assert d["legacy_withdrawals"] == []


def test_withdrawal_flow_and_paid_deducts_balance():
    import db
    import pytest
    _seed_member(db, "w@example.com", "W", balance=100.0)
    r1 = db.create_afi_withdrawal("w@example.com", 30.0, "0x" + "a" * 40)
    assert r1["status"] == "pending"
    assert db.get_afi_member("w@example.com")["balance"] == 100.0  # 申請時は減らない
    with pytest.raises(ValueError):
        db.create_afi_withdrawal("w@example.com", 80.0, "0x" + "a" * 40)  # pending含め超過
    db.update_afi_withdrawal_status(r1["id"], "paid")
    assert db.get_afi_member("w@example.com")["balance"] == 70.0
    # cancel は pending のみ / cancelled 後の変更不可
    r2 = db.create_afi_withdrawal("w@example.com", 70.0, "0x" + "a" * 40)
    assert db.cancel_afi_withdrawal(r2["id"], "w@example.com")
    with pytest.raises(ValueError):
        db.update_afi_withdrawal_status(r2["id"], "paid")


def test_totals_exclude_preview():
    import db
    _seed_member(db, "real@example.com", "R", balance=10.0, kaiin=1, hoihoi=1)
    _seed_member(db, "pv@example.com", "PV", balance=999.0, kaiin=9, hoihoi=9, source="preview")
    t = db.afi_totals()
    assert t["members"] == 1
    assert t["total_balance"] == 10.0
    assert t["total_kaiin_units"] == 1


def test_white_login_non_member_returns_found_false():
    import main
    client = TestClient(main.app)
    r = client.post("/api/white/login", json={"email": "nobody@nowhere.com"})
    assert r.status_code == 200
    assert r.json() == {"found": False}


def test_white_me_requires_white_scope_token():
    import db, auth, main
    _seed_member(db, "sc@example.com", "SC")
    client = TestClient(main.app)
    assert client.get("/api/white/me").status_code == 401
    # portal スコープのトークンでは入れない
    portal_tok = auth.issue_member_token("sc@example.com", scope="portal")
    r = client.get("/api/white/me", headers={"Authorization": f"Bearer {portal_tok['token']}"})
    assert r.status_code == 401
    white_tok = auth.issue_member_token("sc@example.com", scope="white")
    r2 = client.get("/api/white/me", headers={"Authorization": f"Bearer {white_tok['token']}"})
    assert r2.status_code == 200
    assert r2.json()["kaiin_units"] == 4


def test_white_withdraw_api_and_cancel():
    import db, auth, main
    _seed_member(db, "api-w@example.com", "W", balance=80.0)
    tok = auth.issue_member_token("api-w@example.com", scope="white")["token"]
    h = {"Authorization": f"Bearer {tok}"}
    client = TestClient(main.app)
    rw = client.post("/api/white/withdraw",
                     json={"amount": 30, "destination": "0x" + "d" * 40}, headers=h)
    assert rw.status_code == 200, rw.text
    wid = rw.json()["id"]
    rc = client.delete(f"/api/white/withdraw/{wid}", headers=h)
    assert rc.status_code == 200
    assert rc.json()["dashboard"]["withdrawals"][0]["status"] == "cancelled"


def test_white_login_allowlist_blocks_non_listed(monkeypatch):
    import importlib
    import sys
    monkeypatch.setenv("WHITE_ALLOWED_EMAILS", "admin@example.com")
    for m in ("config", "main"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import db, main
    db.init_db()
    _seed_member(db, "blocked@example.com", "B")
    client = TestClient(main.app)
    r = client.post("/api/white/login", json={"email": "blocked@example.com"})
    assert r.json() == {"found": False}
    r2 = client.post("/api/white/verify", json={"email": "blocked@example.com", "code": "123456"})
    assert r2.status_code == 403


def test_import_afi_snapshot_build_members():
    """ETL の集計ロジック（packet合計 / list_user 1エントリ=1口）。"""
    from tools.import_afi_snapshot import build_members
    users = [
        {"id": 1, "email": "a@example.com", "name": "A", "balance": 50.0, "wallet_address": "0xA"},
        {"id": 2, "email": "b@example.com", "name": "B", "balance": 0, "wallet_address": None},
        {"id": 3, "email": "zero@example.com", "name": "Z", "balance": 0, "wallet_address": None},
    ]
    nft = [
        {"user_id": 1, "packet": 4},
        {"user_id": 1, "packet": 1},
        {"user_id": 2, "packet": 2},
    ]
    devices = [
        {"user_id": 1, "packet": 3, "list_user": [
            {"email": "a@example.com"}, {"email": "a@example.com"}, {"email": "c@example.com"},
        ]},
    ]
    members, stats = build_members(users, nft, devices, "2026-07-20T00:00:00")
    by_email = {m["email"]: m for m in members}
    assert by_email["a@example.com"]["kaiin_units"] == 5
    assert by_email["a@example.com"]["hoihoi_units"] == 2
    assert by_email["a@example.com"]["balance"] == 50.0
    assert by_email["b@example.com"]["kaiin_units"] == 2
    # マスタ外の list_user email も 1口として登録される
    assert by_email["c@example.com"]["hoihoi_units"] == 1
    # 残高0・資産0 は投入されない
    assert "zero@example.com" not in by_email
    assert stats["members"] == 3


def test_build_white_ai_block():
    import ai
    white = {
        "balance": 120.5, "kaiin_units": 4, "hoihoi_units": 2,
        "withdrawals": [{"id": 1, "amount": 20.0, "status": "pending"}],
        "legacy_withdrawals": [],
    }
    block = ai._build_white_block(white, is_member=True)
    assert "白のダッシュボード" in block
    assert "会員権NFT: 4 口" in block
    assert "120.50 USDT" in block
    assert "進行中の出金申請: 1 件" in block
    assert "ポータル側の出金処理を優先" in block
    assert ai._build_white_block(None, is_member=True) == ""
