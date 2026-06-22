"""トークン認証。

POST /api/auth/login で username/password を受け取り、HMAC で署名された
ステートレスなトークンを返す。Bearer トークンとして以降のリクエストに付与する。

ADMIN_PASSWORD 未設定なら認証スキップ（開発用、起動時に警告を出す）。
"""
import base64
import hmac
import hashlib
import json
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import ADMIN_USERNAME, ADMIN_PASSWORD
from logging_config import get_logger

log = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)

# トークン署名用のシークレット。プロセス起動ごとに変えると全員ログアウトされるので、
# ADMIN_PASSWORD を派生鍵として使う（ADMIN_PASSWORD が変わるとトークンは無効化される）。
_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 日


def _derive_secret() -> bytes:
    return hashlib.sha256(("betimail:" + ADMIN_PASSWORD).encode("utf-8")).digest()


def issue_token(username: str, ttl_seconds: int = _TOKEN_TTL_SECONDS) -> dict:
    expires_at = int(time.time()) + ttl_seconds
    payload = {"u": username, "exp": expires_at}
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
    sig = hmac.new(_derive_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    token = f"{payload_b64}.{sig_b64}"
    return {"token": token, "expires_at": expires_at, "username": username}


def verify_token(token: str) -> Optional[dict]:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return None
    expected_sig = hmac.new(_derive_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    try:
        given_sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, given_sig):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def issue_member_token(email: str, ttl_seconds: int = _TOKEN_TTL_SECONDS) -> dict:
    """ラッキーマスタード会員ポータル用のステートレストークン（scope=lucky）。"""
    expires_at = int(time.time()) + ttl_seconds
    payload = {"m": email, "scope": "lucky", "exp": expires_at}
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
    sig = hmac.new(_derive_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return {"token": f"{payload_b64}.{sig_b64}", "expires_at": expires_at, "email": email}


def require_lucky_member(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    """会員ポータル用の依存関係。scope=lucky のトークンを検証し email を返す。"""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ログインが必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_token(creds.credentials)
    if payload is None or payload.get("scope") != "lucky" or not payload.get("m"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="セッションが無効または期限切れです。再度ログインしてください",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload["m"]


def check_credentials(username: str, password: str) -> bool:
    if not ADMIN_PASSWORD:
        return False
    ok_user = secrets.compare_digest(username, ADMIN_USERNAME)
    ok_pass = secrets.compare_digest(password, ADMIN_PASSWORD)
    return ok_user and ok_pass


def require_admin(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    """エンドポイントの依存関係。Bearer トークンを検証する。"""
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_PASSWORD が未設定のため管理APIは利用できません",
        )
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証トークンが必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_token(creds.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンが無効または期限切れです",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload.get("u", "user")


def admin_configured() -> bool:
    return bool(ADMIN_PASSWORD)
