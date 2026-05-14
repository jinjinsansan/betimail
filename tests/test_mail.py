"""Resend 呼び出しはモック。プレースホルダ展開とスレッディングヘッダの検証。"""
import mail


def test_text_to_html_escapes_and_brs():
    out = mail._text_to_html("a<b>\nc&d")
    assert "&lt;b&gt;" in out
    assert "<br>" in out
    assert "&amp;" in out


def test_send_bulk_emails_template_placeholders(monkeypatch):
    captured = []

    def fake_send(to_email, to_name, subject, body, headers=None, reply_to=None):
        captured.append({"email": to_email, "subject": subject, "body": body})
        return "id-" + to_email

    monkeypatch.setattr(mail, "send_email", fake_send)

    recipients = [
        {"name": "A", "email": "a@x.com", "nft_type": "会員権NFT"},
        {"name": "B", "email": "b@x.com", "nft_type": "パチスロホイホイNFT"},
    ]
    template = "{name} さん ({nft_type})"
    results = mail.send_bulk_emails(recipients, "件名", template)
    assert len(results) == 2
    assert captured[0]["body"] == "A さん (会員権NFT)"
    assert captured[1]["body"] == "B さん (パチスロホイホイNFT)"
    assert all(r["status"] == "sent" for r in results)


def test_send_bulk_emails_failure_does_not_stop(monkeypatch):
    calls = {"n": 0}

    def fake_send(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return "ok"

    monkeypatch.setattr(mail, "send_email", fake_send)

    recipients = [
        {"name": "A", "email": "a@x", "nft_type": ""},
        {"name": "B", "email": "b@x", "nft_type": ""},
        {"name": "C", "email": "c@x", "nft_type": ""},
    ]
    results = mail.send_bulk_emails(recipients, "s", "b")
    assert [r["status"] for r in results] == ["sent", "error", "sent"]


def test_send_reply_threading_headers(monkeypatch):
    captured = {}

    def fake_send(to_email, to_name, subject, body, headers=None, reply_to=None):
        captured["subject"] = subject
        captured["headers"] = headers
        return "id"

    monkeypatch.setattr(mail, "send_email", fake_send)
    mail.send_reply("a@x", "A", "Original", "reply body", in_reply_to_message_id="msg-abc")
    assert captured["subject"] == "Re: Original"
    assert captured["headers"]["In-Reply-To"] == "<msg-abc>"
    assert captured["headers"]["References"] == "<msg-abc>"
