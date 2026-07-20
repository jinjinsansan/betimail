"""ポータル（betiダッシュボード再構築）のテスト。"""
from fastapi.testclient import TestClient


def _seed_member(db, email="taro@example.com", name="山田太郎", *,
                 balance=100.0, hoihoi=(10, 6), member=(0, 0), source="dump"):
    """会員 + 資産を投入。hoihoi/member は (purchased, staked)。"""
    db.bulk_upsert_portal_members([{
        "email": email, "name": name, "portal_user_id": 1,
        "wallet_address": None, "balance": balance,
        "cumulative_reward": 0.0, "source": source,
    }])
    assets = []
    if hoihoi != (0, 0):
        assets.append({"email": email, "nft_type": "HOIHOI",
                       "purchased_units": hoihoi[0], "staked_units": hoihoi[1]})
    if member != (0, 0):
        assets.append({"email": email, "nft_type": "MEMBER",
                       "purchased_units": member[0], "staked_units": member[1]})
    if assets:
        db.bulk_upsert_portal_assets(assets)
    return email


# ── 分配 ─────────────────────────────────────────────


def test_distribution_prorata_by_staked_units():
    import db
    _seed_member(db, "a@example.com", "A", balance=10.0, hoihoi=(10, 3))
    _seed_member(db, "b@example.com", "B", balance=0.0, hoihoi=(5, 1))
    res = db.create_portal_distribution("HOIHOI", 400.0, created_by="test")
    assert res["total_units"] == 4
    assert res["recipients"] == 2
    a = db.get_portal_member("a@example.com")
    b = db.get_portal_member("b@example.com")
    assert a["balance"] == 310.0   # 10 + 3*100
    assert b["balance"] == 100.0   # 0 + 1*100
    assert a["cumulative_reward"] == 300.0


def test_distribution_only_target_nft_and_skips_unstaked():
    import db
    _seed_member(db, "h@example.com", "H", balance=0.0, hoihoi=(10, 2))
    _seed_member(db, "m@example.com", "M", balance=0.0, hoihoi=(0, 0), member=(10, 5))
    _seed_member(db, "u@example.com", "U", balance=0.0, hoihoi=(10, 0))  # 未ステーク
    res = db.create_portal_distribution("HOIHOI", 200.0, created_by="test")
    assert res["recipients"] == 1
    assert res["total_units"] == 2
    assert db.get_portal_member("m@example.com")["balance"] == 0.0
    assert db.get_portal_member("u@example.com")["balance"] == 0.0


def test_distribution_excludes_preview_and_rejects_bad_nft():
    import db
    import pytest
    _seed_member(db, "real@example.com", "R", balance=0.0, hoihoi=(2, 2))
    _seed_member(db, "pv@example.com", "PV", balance=0.0, hoihoi=(10, 10), source="preview")
    res = db.create_portal_distribution("HOIHOI", 200.0)
    assert res["total_units"] == 2
    assert db.get_portal_member("pv@example.com")["balance"] == 0.0
    with pytest.raises(ValueError):
        db.create_portal_distribution("SPECIAL_MUSTARD", 100.0)
    with pytest.raises(ValueError):
        db.create_portal_distribution("MEMBER", 100.0)  # ステーカー0


# ── ステークボタン ────────────────────────────────────


def test_stake_moves_all_unstaked_units():
    import db
    import pytest
    _seed_member(db, "s@example.com", "S", hoihoi=(10, 6))
    res = db.stake_portal_units("s@example.com", "HOIHOI")
    assert res["staked"] == 4
    assert res["staked_units"] == 10
    assets = db.get_portal_assets("s@example.com")
    assert assets[0]["staked_units"] == 10
    assert assets[0]["unstaked_units"] == 0
    with pytest.raises(ValueError):
        db.stake_portal_units("s@example.com", "HOIHOI")  # もう未ステークが無い


def test_staked_units_join_next_distribution():
    import db
    _seed_member(db, "s2@example.com", "S2", balance=0.0, hoihoi=(10, 0))
    db.stake_portal_units("s2@example.com", "HOIHOI")
    res = db.create_portal_distribution("HOIHOI", 100.0)
    assert res["total_units"] == 10
    assert db.get_portal_member("s2@example.com")["balance"] == 100.0


# ── 買い取り意思表示 ──────────────────────────────────


def test_buyback_request_once_only():
    import db
    import pytest
    _seed_member(db, "bb@example.com", "BB", hoihoi=(10, 6))
    res = db.create_buyback_request("bb@example.com")
    assert res["status"] == "pending"
    assert res["units"] == 10
    with pytest.raises(ValueError):
        db.create_buyback_request("bb@example.com")  # 不可逆・二重申請不可
    assert db.update_buyback_status(res["id"], "confirmed", "確認済み")
    got = db.get_portal_buybacks("bb@example.com")
    assert got[0]["status"] == "confirmed"


def test_buyback_requires_holding():
    import db
    import pytest
    _seed_member(db, "nb@example.com", "NB", hoihoi=(0, 0), member=(5, 5))
    with pytest.raises(ValueError):
        db.create_buyback_request("nb@example.com")


# ── 出金申請 ─────────────────────────────────────────


def test_withdrawal_flow_partial_and_paid_deducts_balance():
    import db
    import pytest
    _seed_member(db, "w@example.com", "W", balance=100.0)
    r1 = db.create_portal_withdrawal("w@example.com", 30.0, "0x" + "a" * 40)
    assert r1["status"] == "pending"
    # 残高は申請時点では減らない
    assert db.get_portal_member("w@example.com")["balance"] == 100.0
    # pending 分を差し引いた申請可能額を超えるとエラー
    with pytest.raises(ValueError):
        db.create_portal_withdrawal("w@example.com", 80.0, "0x" + "a" * 40)
    r2 = db.create_portal_withdrawal("w@example.com", 70.0, "0x" + "a" * 40)
    # paid で残高減算
    db.update_portal_withdrawal_status(r1["id"], "paid")
    assert db.get_portal_member("w@example.com")["balance"] == 70.0
    db.update_portal_withdrawal_status(r2["id"], "paid")
    assert db.get_portal_member("w@example.com")["balance"] == 0.0


def test_withdrawal_cancel_and_guards():
    import db
    import pytest
    _seed_member(db, "w2@example.com", "W2", balance=50.0)
    r = db.create_portal_withdrawal("w2@example.com", 50.0, "0x" + "b" * 40)
    # 本人以外は取り下げ不可
    assert not db.cancel_portal_withdrawal(r["id"], "other@example.com")
    assert db.cancel_portal_withdrawal(r["id"], "w2@example.com")
    # cancelled 後の状態変更は不可
    with pytest.raises(ValueError):
        db.update_portal_withdrawal_status(r["id"], "paid")
    # 取り下げ後は再申請できる
    r2 = db.create_portal_withdrawal("w2@example.com", 50.0, "0x" + "b" * 40)
    assert r2["status"] == "pending"


def test_withdrawal_validation():
    import db
    import pytest
    _seed_member(db, "w3@example.com", "W3", balance=10.0)
    with pytest.raises(ValueError):
        db.create_portal_withdrawal("w3@example.com", 0, "0x" + "c" * 40)
    with pytest.raises(ValueError):
        db.create_portal_withdrawal("w3@example.com", 5, "short")
    with pytest.raises(ValueError):
        db.create_portal_withdrawal("unknown@example.com", 5, "0x" + "c" * 40)


# ── ダッシュボード ────────────────────────────────────


def test_dashboard_shape():
    import db
    _seed_member(db, "d@example.com", "D", balance=55.5, hoihoi=(10, 6))
    db.create_portal_distribution("HOIHOI", 60.0)  # rate 10/口 → +60
    db.create_buyback_request("d@example.com")
    d = db.get_portal_dashboard("d@example.com")
    assert d["balance"] == 115.5
    assert d["assets"][0]["nft_type"] == "HOIHOI"
    assert d["assets"][0]["unstaked_units"] == 4
    assert d["buybacks"][0]["status"] == "pending"
    assert len(d["history"]) == 1
    assert d["history"][0]["amount"] == 60.0


# ── API ──────────────────────────────────────────────


def test_portal_login_non_member_returns_found_false():
    import main
    client = TestClient(main.app)
    r = client.post("/api/portal/login", json={"email": "nobody@nowhere.com"})
    assert r.status_code == 200
    assert r.json() == {"found": False}


def test_portal_me_requires_portal_scope_token():
    import db, auth, main
    _seed_member(db, "sc@example.com", "SC")
    client = TestClient(main.app)
    assert client.get("/api/portal/me").status_code == 401
    # lucky スコープのトークンではポータルに入れない
    lucky_tok = auth.issue_member_token("sc@example.com", scope="lucky")
    r = client.get("/api/portal/me", headers={"Authorization": f"Bearer {lucky_tok['token']}"})
    assert r.status_code == 401
    portal_tok = auth.issue_member_token("sc@example.com", scope="portal")
    r2 = client.get("/api/portal/me", headers={"Authorization": f"Bearer {portal_tok['token']}"})
    assert r2.status_code == 200
    assert r2.json()["email"] == "sc@example.com"


def test_portal_buyback_api_requires_confirm_and_blocks_duplicate():
    import db, auth, main
    _seed_member(db, "api-bb@example.com", "BB", hoihoi=(10, 5))
    tok = auth.issue_member_token("api-bb@example.com", scope="portal")["token"]
    h = {"Authorization": f"Bearer {tok}"}
    client = TestClient(main.app)
    # confirm 無しは 400（「二度と元に戻せません」確認の強制）
    r0 = client.post("/api/portal/buyback", json={"confirm": False}, headers=h)
    assert r0.status_code == 400
    r1 = client.post("/api/portal/buyback", json={"confirm": True}, headers=h)
    assert r1.status_code == 200, r1.text
    assert r1.json()["units"] == 10
    # 二重申請は 409
    r2 = client.post("/api/portal/buyback", json={"confirm": True}, headers=h)
    assert r2.status_code == 409
    # HOIHOI 以外は 400
    r3 = client.post("/api/portal/buyback", json={"confirm": True, "nft_type": "MEMBER"}, headers=h)
    assert r3.status_code == 400


def test_portal_stake_and_withdraw_api():
    import db, auth, main
    _seed_member(db, "api-w@example.com", "W", balance=80.0, hoihoi=(10, 4))
    tok = auth.issue_member_token("api-w@example.com", scope="portal")["token"]
    h = {"Authorization": f"Bearer {tok}"}
    client = TestClient(main.app)
    r = client.post("/api/portal/stake", json={"nft_type": "HOIHOI"}, headers=h)
    assert r.status_code == 200
    assert r.json()["staked"] == 6
    rw = client.post("/api/portal/withdraw",
                     json={"amount": 30, "destination": "0x" + "d" * 40}, headers=h)
    assert rw.status_code == 200, rw.text
    wid = rw.json()["id"]
    # 取り下げ
    rc = client.delete(f"/api/portal/withdraw/{wid}", headers=h)
    assert rc.status_code == 200
    assert rc.json()["dashboard"]["withdrawals"][0]["status"] == "cancelled"


def test_portal_admin_distribute_guard(monkeypatch):
    import importlib
    import sys
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    for m in ("config", "auth", "main"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import db, auth, main
    db.init_db()
    _seed_member(db, "ad@example.com", "AD", balance=0.0, hoihoi=(4, 4))
    token = auth.issue_token("admin")["token"]
    h = {"Authorization": f"Bearer {token}"}
    client = TestClient(main.app)
    # プレビュー
    rp = client.post("/api/portal/admin/distribute/preview",
                     json={"nft_type": "HOIHOI", "amount": 400}, headers=h)
    assert rp.status_code == 200
    assert rp.json()["total_units"] == 4
    assert rp.json()["rate"] == 100.0
    # 実行
    r1 = client.post("/api/portal/admin/distribute",
                     json={"nft_type": "HOIHOI", "amount": 400}, headers=h)
    assert r1.status_code == 200, r1.text
    # 同日同種別は 409
    r2 = client.post("/api/portal/admin/distribute",
                     json={"nft_type": "HOIHOI", "amount": 400}, headers=h)
    assert r2.status_code == 409
    # force で実行可
    r3 = client.post("/api/portal/admin/distribute",
                     json={"nft_type": "HOIHOI", "amount": 400, "force": True}, headers=h)
    assert r3.status_code == 200
    assert db.get_portal_member("ad@example.com")["balance"] == 800.0


def test_portal_login_allowlist_blocks_non_listed(monkeypatch):
    import importlib
    import sys
    monkeypatch.setenv("PORTAL_ALLOWED_EMAILS", "admin@example.com")
    for m in ("config", "main"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import db, main
    db.init_db()
    _seed_member(db, "blocked@example.com", "B")
    client = TestClient(main.app)
    r = client.post("/api/portal/login", json={"email": "blocked@example.com"})
    assert r.json() == {"found": False}
    r2 = client.post("/api/portal/verify", json={"email": "blocked@example.com", "code": "123456"})
    assert r2.status_code == 403
