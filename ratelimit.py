"""シンプルなインメモリのトークンバケットレートリミッタ。
プロセス単一なので分散環境では不向きだが、本アプリの規模では十分。"""
import threading
import time
from collections import defaultdict
from fastapi import HTTPException, Request, status

_lock = threading.Lock()
_buckets: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(key: str, max_calls: int, window_seconds: float, identifier: str = "") -> None:
    """指定 key と識別子 (例: IP) で max_calls / window_seconds を超えたら 429。"""
    bucket_key = f"{key}:{identifier}"
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        bucket = _buckets[bucket_key]
        # 古いエントリを破棄
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= max_calls:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"レート制限超過: {max_calls} req / {window_seconds:.0f}s",
            )
        bucket.append(now)


def limit_webhook(request: Request) -> None:
    rate_limit("webhook", max_calls=60, window_seconds=60.0, identifier=_client_ip(request))


def limit_send(request: Request) -> None:
    rate_limit("send", max_calls=10, window_seconds=60.0, identifier=_client_ip(request))


def limit_public_check(request: Request) -> None:
    """公開エンドポイント（メルマガ配信チェック）の濫用防止: 20回/分/IP。"""
    rate_limit("public_check", max_calls=20, window_seconds=60.0, identifier=_client_ip(request))
