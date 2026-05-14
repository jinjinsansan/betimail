"""Webhook 署名検証のテスト。"""
import base64
import hashlib
import hmac
import time
import importlib


def test_verify_with_correct_signature(monkeypatch):
    secret = "whsec_" + base64.b64encode(b"my-secret-key").decode()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    import config
    importlib.reload(config)
    import webhook
    importlib.reload(webhook)

    svix_id = "msg_abc"
    ts = str(int(time.time()))
    body = b'{"hello":"world"}'

    raw = base64.b64decode("my-secret-key" + "==" if not base64.b64encode(b"my-secret-key").decode().endswith("=") else base64.b64encode(b"my-secret-key").decode())
    raw_secret = base64.b64decode(base64.b64encode(b"my-secret-key").decode())
    signed = f"{svix_id}.{ts}.{body.decode()}".encode()
    sig = base64.b64encode(hmac.new(raw_secret, signed, hashlib.sha256).digest()).decode()
    header = f"v1,{sig}"

    assert webhook.verify_signature(svix_id, ts, header, body) is True


def test_verify_rejects_bad_signature(monkeypatch):
    secret = "whsec_" + base64.b64encode(b"my-secret").decode()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    import config
    importlib.reload(config)
    import webhook
    importlib.reload(webhook)

    ts = str(int(time.time()))
    body = b'{"x":1}'
    assert webhook.verify_signature("m", ts, "v1,deadbeef", body) is False


def test_verify_rejects_stale_timestamp(monkeypatch):
    secret = "whsec_" + base64.b64encode(b"s").decode()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    import config
    importlib.reload(config)
    import webhook
    importlib.reload(webhook)

    old_ts = str(int(time.time()) - 3600)
    assert webhook.verify_signature("m", old_ts, "v1,sig", b"{}") is False


def test_unset_secret_passes_through(monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "")
    import config
    importlib.reload(config)
    import webhook
    importlib.reload(webhook)

    assert webhook.verify_signature("", "", "", b"") is True
