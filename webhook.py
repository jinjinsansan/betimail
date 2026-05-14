"""Resend Webhook 署名検証 (Svix 互換)。

Resend は Svix を使って webhook を配信している。検証する署名のヘッダは:
- svix-id
- svix-timestamp
- svix-signature  (space-separated, 各値は "v1,base64sig" 形式)

検証手順:
  signed_content = f"{svix_id}.{svix_timestamp}.{body_bytes_decoded_utf8}"
  expected = HMAC-SHA256(secret_bytes, signed_content) -> base64
  与えられた signature の中に "v1,{expected}" があれば OK
"""
import base64
import hashlib
import hmac
import time
from fastapi import HTTPException, Request, status
from config import RESEND_WEBHOOK_SECRET
from logging_config import get_logger

log = get_logger(__name__)

# Svix シークレットは "whsec_xxxxx" 形式。base64 部分のみ使う。
_TOLERANCE_SECONDS = 5 * 60  # ±5 分


def _decode_secret(secret: str) -> bytes:
    if not secret:
        return b""
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_"):]
    try:
        return base64.b64decode(secret)
    except Exception:
        # base64 でなくプレーン文字列のパターンもサポート
        return secret.encode("utf-8")


def verify_signature(svix_id: str, svix_timestamp: str, svix_signature: str, body: bytes) -> bool:
    if not RESEND_WEBHOOK_SECRET:
        return True  # 未設定なら検証スキップ（dev 用）
    if not (svix_id and svix_timestamp and svix_signature):
        return False

    # タイムスタンプの新鮮さチェック
    try:
        ts = int(svix_timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > _TOLERANCE_SECONDS:
        return False

    secret_bytes = _decode_secret(RESEND_WEBHOOK_SECRET)
    signed_content = f"{svix_id}.{svix_timestamp}.{body.decode('utf-8', errors='replace')}".encode("utf-8")
    expected = base64.b64encode(
        hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    ).decode()

    # svix-signature は "v1,sig v1,sig2" のように複数を含み得る
    for part in svix_signature.split():
        if "," not in part:
            continue
        version, sig = part.split(",", 1)
        if version != "v1":
            continue
        if hmac.compare_digest(sig, expected):
            return True
    return False


async def verify_webhook_request(request: Request) -> bytes:
    """検証 OK なら body bytes を返す。NG なら 401。bodyを後段でJSON化して使うため。"""
    body = await request.body()
    if not RESEND_WEBHOOK_SECRET:
        log.warning("RESEND_WEBHOOK_SECRET unset; webhook signature NOT verified")
        return body
    svix_id = request.headers.get("svix-id", "")
    svix_ts = request.headers.get("svix-timestamp", "")
    svix_sig = request.headers.get("svix-signature", "")
    if not verify_signature(svix_id, svix_ts, svix_sig, body):
        log.warning("Webhook signature verification failed (id=%s ts=%s)", svix_id, svix_ts)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
    return body
