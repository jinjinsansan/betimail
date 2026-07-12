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
