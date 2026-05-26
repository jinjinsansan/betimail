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
