"""AI モジュールのフォールバックパーサーテスト（API キーなしで実行可能な範囲）。"""
import ai


def test_fallback_plain_json():
    text = '{"reply":"hi","confidence":0.9,"needs_human":false}'
    r = ai._fallback_parse(text)
    assert r["reply"] == "hi"
    assert r["confidence"] == 0.9
    assert r["needs_human"] is False


def test_fallback_code_block():
    text = '```json\n{"reply":"hi","confidence":0.5,"needs_human":true,"reason":"x"}\n```'
    r = ai._fallback_parse(text)
    assert r["reason"] == "x"


def test_fallback_garbage_falls_through():
    r = ai._fallback_parse("This is not JSON at all.")
    assert r["needs_human"] is True
    assert r["confidence"] == 0.0


def test_generate_reply_without_api_key(monkeypatch):
    monkeypatch.setattr(ai, "client", None)
    r = ai.generate_reply(
        sender_name="A", sender_email="a@b", nft_type="会員権NFT",
        original_subject="?", original_body="hi",
    )
    assert r["needs_human"] is True
    assert "DEEPSEEK_API_KEY" in r["reason"]


def _lucky_fixture():
    return {
        "email": "a@b",
        "name": "テスト太郎",
        "nft_count": 5,
        "owned_nft": 8,
        "balance": 1234.56,
        "cumulative_reward": 987.65,
        "today_reward": 2.57,
        "rate": 0.5139,
        "last_reward_at": "2026-07-12 20:00:00",
        "history": [],
        "series": [],
    }


def test_format_lucky_summary_contains_key_figures():
    text = ai._format_lucky_summary(_lucky_fixture())
    assert "5 枚" in text                    # 報酬対象（ステーク）枚数
    assert "8 枚" in text                    # 購入枚数（乖離があるので併記）
    assert "1,234.56 USDT" in text           # 残高
    assert "987.65 USDT" in text             # 累計報酬
    assert "2026-07-12" in text              # 最終報酬入金日


def test_format_lucky_summary_omits_owned_when_equal():
    lucky = _lucky_fixture()
    lucky["owned_nft"] = 5  # ステーク数と同じなら併記しない
    text = ai._format_lucky_summary(lucky)
    assert "累計購入枚数" not in text


def test_build_lucky_block_registered_member():
    block = ai._build_lucky_block(_lucky_fixture(), is_member=True)
    assert "ポータル登録データ" in block
    assert "admin.betimail.uk/lucky" in block


def test_build_lucky_block_member_without_lucky():
    block = ai._build_lucky_block(None, is_member=True)
    assert "登録されていません" in block
    assert "needs_human" in block


def test_build_lucky_block_non_member_without_lucky():
    assert ai._build_lucky_block(None, is_member=False) == ""


def test_knowledge_base_mentions_lucky_portal():
    """知識ベースにポータルの案内が含まれている（システムプロンプトに投入される）。"""
    prompt = ai._build_system_prompt()
    assert "https://admin.betimail.uk/lucky" in prompt
    assert "出金機能は現在未提供" in prompt


# ── ポータル（betiダッシュボード）ブロック ──────────────


def _portal_fixture():
    return {
        "email": "taro@example.com",
        "name": "山田太郎",
        "balance": 250.75,
        "cumulative_reward": 100.5,
        "assets": [
            {"nft_type": "HOIHOI", "purchased_units": 10, "staked_units": 6,
             "transferred_in": 0, "transferred_out": 0, "unstaked_units": 4},
            {"nft_type": "MEMBER", "purchased_units": 20, "staked_units": 20,
             "transferred_in": 0, "transferred_out": 0, "unstaked_units": 0},
        ],
        "buybacks": [
            {"id": 1, "nft_type": "HOIHOI", "units": 10, "status": "pending",
             "requested_at": "2026-07-20T10:00:00"},
        ],
        "withdrawals": [
            {"id": 1, "amount": 50.0, "status": "pending", "requested_at": "2026-07-20"},
        ],
        "legacy_withdrawals": [],
        "history": [],
    }


def test_format_portal_summary_contains_assets_and_requests():
    text = ai._format_portal_summary(_portal_fixture())
    assert "パチスロホイホイNFT" in text
    assert "購入 10 口" in text
    assert "ステーク済み 6 口" in text
    assert "250.75 USDT" in text
    assert "買い取り申請あり" in text
    assert "申請受付" in text
    assert "取り消し不可" in text
    assert "進行中の出金申請: 1 件" in text


def test_build_portal_block_registered_member():
    block = ai._build_portal_block(_portal_fixture(), is_member=True)
    assert "betiダッシュボード" in block
    assert "取り消せません" in block


def test_build_portal_block_member_without_portal():
    block = ai._build_portal_block(None, is_member=True)
    assert "登録されていません" in block
    assert "needs_human" in block


def test_build_portal_block_non_member_without_portal():
    assert ai._build_portal_block(None, is_member=False) == ""
