"""HTTP Basic 認証。ADMIN_PASSWORD 未設定なら認証スキップ（開発用）。"""
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from config import ADMIN_USERNAME, ADMIN_PASSWORD
from logging_config import get_logger

log = get_logger(__name__)
_security = HTTPBasic(auto_error=False)


def require_admin(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    if not ADMIN_PASSWORD:
        # 未設定なら認証なしで通す（最初の起動を妨げないため、起動時に WARN を出す）
        return "anonymous"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です",
            headers={"WWW-Authenticate": "Basic"},
        )

    ok_user = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        log.warning("Failed admin login attempt: user=%s", credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが違います",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def admin_configured() -> bool:
    return bool(ADMIN_PASSWORD)
