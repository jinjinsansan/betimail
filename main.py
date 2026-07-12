"""FastAPI エントリポイント。"""
import asyncio
import hashlib
import hmac
import json
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone, timedelta
from email.utils import getaddresses
from typing import Optional

from fastapi import (
    FastAPI, Request, HTTPException, BackgroundTasks, Depends, Response,
    UploadFile, File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field, field_validator

from logging_config import setup_logging, get_logger

setup_logging()
log = get_logger(__name__)

import db
import members as mbr
import mail
import ai
import telegram_bot
import auth as auth_mod
from auth import require_admin, admin_configured, check_credentials, issue_token
from ratelimit import limit_webhook, limit_send, limit_public_check, limit_login
from webhook import verify_webhook_request
from config import (
    NFT_TYPES, TELEGRAM_BOT_TOKEN, SEND_WELCOME_EMAIL,
    CORS_ORIGINS, CORS_ORIGIN_REGEX, AI_HISTORY_DEPTH,
    PUBLIC_CHECK_EXPOSE_DETAILS, PUBLIC_CHECK_EXPOSE_NAME, PUBLIC_CHECK_EXPOSE_NFT_TYPES,
    PUBLIC_CHECK_REQUIRE_OTP, PUBLIC_CHECK_OTP_TTL_SECONDS, PUBLIC_CHECK_OTP_RESEND_SECONDS,
    RESEND_API_KEY, RESEND_FROM_EMAIL, RESEND_INBOUND_DOMAINS,
    LUCKY_PORTAL_ALLOWED_EMAILS,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if not admin_configured():
        log.warning("ADMIN_PASSWORD が未設定です。管理APIは 503 で拒否されます。")
    bot_thread = None
    if TELEGRAM_BOT_TOKEN:
        bot_thread = telegram_bot.start_bot_thread()
    try:
        yield
    finally:
        try:
            await telegram_bot.shutdown_bot()
        except Exception:
            log.exception("Shutdown failure")


app = FastAPI(title="Betimail - NFTコミュニティサポート", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# CORS: Vercel フロントなど別オリジンからのアクセスを許可
if CORS_ORIGINS or CORS_ORIGIN_REGEX:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_origin_regex=CORS_ORIGIN_REGEX or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ── 画面 (legacy) ───────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """旧UI。Vercel化後は廃止予定だが当面残す。"""
    import os
    if not os.path.exists("templates/index.html"):
        return HTMLResponse(
            "<h1>Betimail API</h1><p>このバックエンドはAPIサーバーです。"
            "管理画面は別途デプロイされたフロントエンドからアクセスしてください。</p>",
        )
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "admin_auth_enabled": admin_configured(),
        "telegram_enabled": bool(TELEGRAM_BOT_TOKEN),
        "version": "1.0",
    }


# ── 公開エンドポイント (ユーザーセルフチェック) ──────────
class PublicCheckRequest(BaseModel):
    email: EmailStr


class PublicCheckVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


_public_check_lock = threading.Lock()
_public_check_otps: dict[str, dict] = {}


def _mask_email(email: str) -> str:
    local, _, domain = (email or "").partition("@")
    if not domain:
        return "***"
    if len(local) <= 2:
        local_masked = "*" * len(local)
    else:
        local_masked = local[:2] + "*" * max(1, len(local) - 2)
    return f"{local_masked}@{domain}"


def _cleanup_public_check_otps(now_ts: float) -> None:
    expired = [
        e for e, rec in _public_check_otps.items()
        if rec.get("expires_at", 0) < now_ts
    ]
    for e in expired:
        _public_check_otps.pop(e, None)


def _build_public_check_result(email: str) -> dict:
    member = mbr.get_member_by_email(email)
    if not member:
        return {"found": False}

    summary = db.get_purchase_summary(member["email"])
    nft_types = [row["nft_type"] for row in summary.get("by_nft", [])]
    ordered = []
    for t in NFT_TYPES:
        if t in nft_types and t not in ordered:
            ordered.append(t)

    data: dict = {"found": True}
    expose_name = PUBLIC_CHECK_EXPOSE_DETAILS or PUBLIC_CHECK_EXPOSE_NAME
    expose_nft = PUBLIC_CHECK_EXPOSE_DETAILS or PUBLIC_CHECK_EXPOSE_NFT_TYPES
    if expose_name:
        data["name"] = member["name"]
    if expose_nft:
        data["nft_types"] = ordered
    return data


def _issue_public_check_otp(email: str) -> str:
    now_ts = time.time()
    with _public_check_lock:
        _cleanup_public_check_otps(now_ts)
        rec = _public_check_otps.get(email)
        if rec and (now_ts - rec.get("issued_at", 0)) < PUBLIC_CHECK_OTP_RESEND_SECONDS:
            raise HTTPException(status_code=429, detail="確認コードの再送は少し待ってからお試しください")

        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_hex(8)
        digest = hashlib.sha256((salt + code).encode("utf-8")).hexdigest()
        _public_check_otps[email] = {
            "salt": salt,
            "digest": digest,
            "issued_at": now_ts,
            "expires_at": now_ts + max(60, PUBLIC_CHECK_OTP_TTL_SECONDS),
            "tries": 0,
        }
        return code


def _verify_public_check_otp(email: str, code: str) -> bool:
    now_ts = time.time()
    normalized = (code or "").strip()
    with _public_check_lock:
        _cleanup_public_check_otps(now_ts)
        rec = _public_check_otps.get(email)
        if not rec:
            return False
        rec["tries"] = int(rec.get("tries", 0)) + 1
        if rec["tries"] > 8:
            _public_check_otps.pop(email, None)
            return False
        digest = hashlib.sha256((rec["salt"] + normalized).encode("utf-8")).hexdigest()
        if not hmac.compare_digest(rec["digest"], digest):
            return False
        _public_check_otps.pop(email, None)
        return True


@app.post("/api/public/check")
async def api_public_check(
    body: PublicCheckRequest,
    request: Request,
):
    """メルマガ配信対象者かどうかをユーザー自身が確認できる公開API。

    レート制限あり (20回/分/IP)。返却内容は本人特定可能だが、
    既に閉じたコミュニティ内の保有情報のため、emailを知っている人にのみ
    意味のある情報。Telegram/メール送信機能は提供しない。
    """
    email = str(body.email).strip().lower()
    limit_public_check(request, email)
    await asyncio.sleep(0.2)

    if not PUBLIC_CHECK_REQUIRE_OTP:
        return _build_public_check_result(email)

    # 非メンバーには OTP を送らない（無関係な人へのメール送信を防止）。
    # 「OTP 必須」と「即 found:false」を返し分けることで列挙の手掛かりは
    # 与えるが、メアドそのものを所持していない第三者には実害がない上、
    # rate-limit で大量ピングは抑止できる。
    if not mbr.get_member_by_email(email):
        return {"found": False}

    if not RESEND_API_KEY or not RESEND_FROM_EMAIL:
        raise HTTPException(status_code=503, detail="確認機能は一時的に利用できません")

    code = _issue_public_check_otp(email)
    body_text = (
        "beti 配信チェックの確認コードです。\n\n"
        f"確認コード: {code}\n"
        f"有効期限: {max(60, PUBLIC_CHECK_OTP_TTL_SECONDS) // 60} 分\n\n"
        "このコードに心当たりがない場合は破棄してください。"
    )
    try:
        mail.send_email(
            to_email=email,
            to_name="",
            subject="【beti】配信チェック確認コード",
            body=body_text,
        )
    except Exception:
        log.exception("Public check OTP send failure")
        raise HTTPException(status_code=503, detail="確認コード送信に失敗しました。時間をおいて再試行してください")

    return {
        "verification_required": True,
        "masked_email": _mask_email(email),
        "expires_in": max(60, PUBLIC_CHECK_OTP_TTL_SECONDS),
    }


@app.post("/api/public/check/verify")
async def api_public_check_verify(
    body: PublicCheckVerifyRequest,
    request: Request,
):
    email = str(body.email).strip().lower()
    limit_public_check(request, email)
    await asyncio.sleep(0.2)
    if not PUBLIC_CHECK_REQUIRE_OTP:
        return _build_public_check_result(email)
    if not _verify_public_check_otp(email, body.code):
        raise HTTPException(status_code=400, detail="確認コードが無効または期限切れです")
    return _build_public_check_result(email)


# ── ラッキーマスタード会員ポータル ──────────────────────
# 会員のみがログインして自分の保有NFT(ステーク)枚数・日次報酬・残高・履歴を閲覧する。
# 認証はメール OTP（_lucky_otps に分離）→ 成功で会員トークン(scope=lucky)を発行。
_lucky_otp_lock = threading.Lock()
_lucky_otps: dict[str, dict] = {}


class LuckyLoginRequest(BaseModel):
    email: EmailStr


class LuckyVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class LuckyDistributeRequest(BaseModel):
    amount: float = Field(gt=0, le=100000)
    distributed_for: Optional[str] = None
    force: bool = False


def _lucky_access_allowed(email: str) -> bool:
    """ソフトローンチ用のアクセス制限。LUCKY_PORTAL_ALLOWED_EMAILS が空なら全員公開、
    非空ならそのリストに含まれるアドレスのみ許可（管理者限定公開）。"""
    if not LUCKY_PORTAL_ALLOWED_EMAILS:
        return True
    return email.strip().lower() in LUCKY_PORTAL_ALLOWED_EMAILS


def _issue_lucky_otp(email: str) -> str:
    now_ts = time.time()
    with _lucky_otp_lock:
        for e in [e for e, r in _lucky_otps.items() if r.get("expires_at", 0) < now_ts]:
            _lucky_otps.pop(e, None)
        rec = _lucky_otps.get(email)
        if rec and (now_ts - rec.get("issued_at", 0)) < PUBLIC_CHECK_OTP_RESEND_SECONDS:
            raise HTTPException(status_code=429, detail="確認コードの再送は少し待ってからお試しください")
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_hex(8)
        _lucky_otps[email] = {
            "salt": salt,
            "digest": hashlib.sha256((salt + code).encode("utf-8")).hexdigest(),
            "issued_at": now_ts,
            "expires_at": now_ts + max(60, PUBLIC_CHECK_OTP_TTL_SECONDS),
            "tries": 0,
        }
        return code


def _verify_lucky_otp(email: str, code: str) -> bool:
    now_ts = time.time()
    normalized = (code or "").strip()
    with _lucky_otp_lock:
        rec = _lucky_otps.get(email)
        if not rec or rec.get("expires_at", 0) < now_ts:
            _lucky_otps.pop(email, None)
            return False
        rec["tries"] = int(rec.get("tries", 0)) + 1
        if rec["tries"] > 8:
            _lucky_otps.pop(email, None)
            return False
        digest = hashlib.sha256((rec["salt"] + normalized).encode("utf-8")).hexdigest()
        if not hmac.compare_digest(rec["digest"], digest):
            return False
        _lucky_otps.pop(email, None)
        return True


@app.post("/api/lucky/login")
async def api_lucky_login(body: LuckyLoginRequest, request: Request):
    """会員のメール OTP ログイン要求。ラッキーマスタード会員のみコードを送信する。"""
    email = str(body.email).strip().lower()
    limit_public_check(request, email)
    await asyncio.sleep(0.2)
    # ソフトローンチ中は許可リスト外を会員と同様に弾く（OTPも送らない）
    if not _lucky_access_allowed(email):
        return {"found": False}
    # 会員でなければコードを送らない（無関係な人へのメール送信を防止）
    if not db.get_lucky_member(email):
        return {"found": False}
    if not RESEND_API_KEY or not RESEND_FROM_EMAIL:
        raise HTTPException(status_code=503, detail="ログイン機能は一時的に利用できません")
    code = _issue_lucky_otp(email)
    body_text = (
        "ラッキーマスタード 会員ページのログインコードです。\n\n"
        f"ログインコード: {code}\n"
        f"有効期限: {max(60, PUBLIC_CHECK_OTP_TTL_SECONDS) // 60} 分\n\n"
        "このコードに心当たりがない場合は破棄してください。"
    )
    try:
        mail.send_email(
            to_email=email, to_name="",
            subject="【ラッキーマスタード】ログインコード", body=body_text,
        )
    except Exception:
        log.exception("Lucky login OTP send failure")
        raise HTTPException(status_code=503, detail="コード送信に失敗しました。時間をおいて再試行してください")
    return {
        "verification_required": True,
        "masked_email": _mask_email(email),
        "expires_in": max(60, PUBLIC_CHECK_OTP_TTL_SECONDS),
    }


@app.post("/api/lucky/verify")
async def api_lucky_verify(body: LuckyVerifyRequest, request: Request):
    """OTP 検証 → 会員トークン発行 + ダッシュボードを返す。"""
    email = str(body.email).strip().lower()
    limit_public_check(request, email)
    await asyncio.sleep(0.2)
    if not _lucky_access_allowed(email):
        raise HTTPException(status_code=403, detail="現在この会員ページは限定公開中です")
    if not _verify_lucky_otp(email, body.code):
        raise HTTPException(status_code=400, detail="コードが無効または期限切れです")
    dash = db.get_lucky_dashboard(email)
    if not dash:
        raise HTTPException(status_code=404, detail="会員情報が見つかりません")
    tok = auth_mod.issue_member_token(email)
    return {"token": tok["token"], "expires_at": tok["expires_at"], "dashboard": dash}


@app.get("/api/lucky/me")
async def api_lucky_me(email: str = Depends(auth_mod.require_lucky_member)):
    """会員トークンで自分のダッシュボードを再取得。"""
    if not _lucky_access_allowed(email):
        raise HTTPException(status_code=403, detail="現在この会員ページは限定公開中です")
    dash = db.get_lucky_dashboard(email)
    if not dash:
        raise HTTPException(status_code=404, detail="会員情報が見つかりません")
    return dash


@app.post("/api/lucky/distribute")
async def api_lucky_distribute(
    body: LuckyDistributeRequest,
    _admin: str = Depends(require_admin),
):
    """管理者: 日次報酬を全保有者へステーク枚数比例で分配する。

    同じ日に二重分配しないよう、対象日(JST)に既存があれば 409 を返す。
    force=true で上書き実行できる。
    """
    if body.distributed_for:
        target = body.distributed_for
        date_str = target[:10]
    else:
        date_str = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
        target = f"{date_str} 20:00:00"
    if not body.force and db.lucky_distribution_exists_for_date(date_str):
        raise HTTPException(
            status_code=409,
            detail=f"{date_str} は既に分配済みです。再度分配する場合は確認のうえ実行してください。",
        )
    try:
        result = db.create_lucky_distribution(
            body.amount, created_by="admin", distributed_for=target,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log.info("Lucky distribution by admin: %s", result)
    return result


@app.get("/api/lucky/distributions")
async def api_lucky_distributions(_admin: str = Depends(require_admin), limit: int = 60):
    return {"distributions": db.list_lucky_distributions(limit=limit)}


@app.get("/api/lucky/admin/summary")
async def api_lucky_admin_summary(_admin: str = Depends(require_admin)):
    totals = db.lucky_totals()
    latest = db.get_latest_lucky_distribution()
    return {"totals": totals, "latest_distribution": latest}


# ── 認証 ────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def api_login(
    body: LoginRequest,
    _rl=Depends(limit_login),
):
    if not admin_configured():
        raise HTTPException(
            status_code=503,
            detail="ADMIN_PASSWORD が未設定です。サーバー側で設定してください。",
        )
    if not check_credentials(body.username, body.password):
        log.warning("Login failed for user=%s", body.username)
        raise HTTPException(status_code=401, detail="ユーザー名またはパスワードが違います")
    token = issue_token(body.username)
    log.info("Login OK for user=%s", body.username)
    return token


@app.get("/api/auth/check")
async def api_auth_check(user: str = Depends(require_admin)):
    return {"username": user, "ok": True}


# ── メンバーAPI ─────────────────────────────────────────
def _normalize_nft_types_value(v: str) -> str:
    raw = [t.strip() for t in (v or "").split(",") if t.strip()]
    if not raw:
        raise ValueError("NFT種別は必須です")
    unknown = [t for t in raw if t not in NFT_TYPES]
    if unknown:
        raise ValueError(f"不正なNFT種別: {', '.join(unknown)}")
    ordered = []
    for t in NFT_TYPES:
        if t in raw and t not in ordered:
            ordered.append(t)
    return ", ".join(ordered)


class MemberCreate(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    nft_type: str
    joined_date: str = ""
    notes: str = ""

    @field_validator("nft_type")
    @classmethod
    def validate_nft(cls, v: str) -> str:
        return _normalize_nft_types_value(v)

    @field_validator("joined_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        if not v:
            return v
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("日付は YYYY-MM-DD 形式で指定してください")
        return v


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    nft_type: Optional[str] = None
    joined_date: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("nft_type")
    @classmethod
    def validate_nft(cls, v):
        if v is None:
            return v
        return _normalize_nft_types_value(v)


@app.get("/api/members")
async def api_get_members(
    nft_type: Optional[str] = None,
    segment: Optional[str] = None,
    _user: str = Depends(require_admin),
):
    if segment:
        return mbr.get_members_by_segment(segment)
    if nft_type:
        return mbr.get_members_by_nft_type(nft_type)
    return mbr.get_all_members()


@app.post("/api/members")
async def api_add_member(body: MemberCreate, bg: BackgroundTasks, _user: str = Depends(require_admin)):
    try:
        member = mbr.add_member(**body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if SEND_WELCOME_EMAIL:
        def _welcome():
            try:
                subject = "ご加入ありがとうございます"
                body_text = (
                    f"{member['name']} 様\n\n"
                    f"NFTコミュニティへのご加入、誠にありがとうございます。\n"
                    f"保有NFT: {member['nft_type']}\n\n"
                    f"今後ともよろしくお願いいたします。\n\n"
                    f"運営チーム"
                )
                resend_id = mail.send_email(member["email"], member["name"], subject, body_text)
                db.record_sent_email(
                    recipient_email=member["email"],
                    recipient_name=member["name"],
                    nft_type=member["nft_type"],
                    subject=subject,
                    body=body_text,
                    resend_id=resend_id,
                )
            except Exception:
                log.exception("Welcome email failure for %s", member["email"])
        bg.add_task(_welcome)
    return member


@app.put("/api/members/{email:path}")
async def api_update_member(email: str, body: MemberUpdate, _user: str = Depends(require_admin)):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="更新項目が指定されていません")
    try:
        updated = mbr.update_member(email, **payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    return updated


@app.delete("/api/members/{email:path}")
async def api_delete_member(email: str, _user: str = Depends(require_admin)):
    if not mbr.delete_member(email):
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    return {"status": "deleted"}


@app.get("/api/members/{email:path}/history")
async def api_member_history(email: str, _user: str = Depends(require_admin)):
    member = mbr.get_member_by_email(email)
    if not member:
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    history = db.get_member_history(email)
    return {"member": member, **history}


@app.get("/api/members/{email:path}/purchases")
async def api_member_purchases(email: str, _user: str = Depends(require_admin)):
    member = mbr.get_member_by_email(email)
    if not member:
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    purchases = db.get_purchases_by_email(email)
    summary = db.get_purchase_summary(email)
    return {"member": member, "purchases": purchases, "summary": summary}


@app.get("/api/members/{email:path}/withdraws")
async def api_member_withdraws(email: str, _user: str = Depends(require_admin)):
    member = mbr.get_member_by_email(email)
    if not member:
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    summary = db.get_withdraw_summary_by_email(email)
    return summary


# ── 出金申請 (買い取り資金支払い) ─────────────────────────
@app.get("/api/withdraws")
async def api_list_withdraws(
    limit: int = 200,
    email: Optional[str] = None,
    source: Optional[str] = "nftportal",
    _user: str = Depends(require_admin),
):
    # source 既定は nftportal（ポータルサイト=買い取り）。afi はアフィリエイト出金を
    # 別ページで閲覧するための値。"all"/空 で全件。
    if source in ("", "all"):
        source = None
    items = db.list_withdraws(limit=limit, email=email, source=source)
    # 集計
    total_usdt = sum((r["amount_usdt"] or 0) for r in items)
    by_email: dict[str, dict] = {}
    for r in items:
        e = r["email"]
        b = by_email.setdefault(e, {
            "email": e, "name": r.get("name"),
            "count": 0, "total_usdt": 0.0,
        })
        b["count"] += 1
        b["total_usdt"] += (r["amount_usdt"] or 0)
    by_recipient = sorted(by_email.values(), key=lambda x: -x["total_usdt"])
    return {
        "items": items,
        "total_count": len(items),
        "total_usdt": total_usdt,
        "by_recipient": by_recipient,
    }


@app.get("/api/withdraws/stats")
async def api_withdraw_stats(
    source: Optional[str] = "nftportal",
    _user: str = Depends(require_admin),
):
    """ダッシュボード用の集計のみ。"""
    if source in ("", "all"):
        source = None
    items = db.list_withdraws(limit=10000, source=source)
    total = sum((r["amount_usdt"] or 0) for r in items)
    return {
        "count": len(items),
        "total_usdt": total,
        "unique_recipients": len({r["email"] for r in items}),
    }


@app.post("/api/members/import")
async def api_import_members(file: UploadFile = File(...), _user: str = Depends(require_admin)):
    content = (await file.read()).decode("utf-8-sig")
    return mbr.import_csv(content)


@app.get("/api/members/export.csv")
async def api_export_members(_user: str = Depends(require_admin)):
    return PlainTextResponse(
        mbr.export_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="members.csv"'},
    )


# ── プレビュー ──────────────────────────────────────────
class PreviewRequest(BaseModel):
    body: str
    sample: dict = {}


@app.post("/api/preview")
async def api_preview(body: PreviewRequest, _user: str = Depends(require_admin)):
    """{name}/{nft_type}/{email} をサンプル値で置換した結果を返す。"""
    members = mbr.get_all_members()
    sample = body.sample if body.sample else (members[0] if members else {
        "name": "サンプル太郎", "email": "sample@example.com", "nft_type": "会員権NFT",
    })
    try:
        rendered = body.body.format(
            name=sample.get("name", ""),
            nft_type=sample.get("nft_type", ""),
            email=sample.get("email", ""),
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"未知のプレースホルダ: {e}")
    return {"rendered": rendered, "sample": sample}


# ── 一括送信 ────────────────────────────────────────────
class SendEmailRequest(BaseModel):
    nft_types: list[str] = []
    segment: Optional[str] = None  # "lucky_only" | "lucky_and_special"
    confirm_all: bool = False
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    # ISO8601 UTC (例: "2026-05-16T11:30:00+00:00")。
    # 指定された場合は予約ジョブとして登録のみし、cron worker が時刻到達時に実行する。
    scheduled_at: Optional[str] = None


@app.post("/api/send")
async def api_send_email(
    body: SendEmailRequest,
    bg: BackgroundTasks,
    request: Request,
    _rl=Depends(limit_send),
    _user: str = Depends(require_admin),
):
    # scheduled_at の検証 (UTC ISO8601、未来時刻、5分以上先、30日以内)
    scheduled_utc_iso: Optional[str] = None
    if body.scheduled_at:
        try:
            sched_dt = datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="scheduled_at の形式が不正です")
        if sched_dt.tzinfo is None:
            raise HTTPException(status_code=400, detail="scheduled_at はタイムゾーン付きで指定してください")
        sched_utc = sched_dt.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)
        delta = (sched_utc - now_utc).total_seconds()
        if delta < 60:
            raise HTTPException(status_code=400, detail="予約時刻は現在から1分以上先に設定してください")
        if delta > 60 * 60 * 24 * 30:
            raise HTTPException(status_code=400, detail="予約時刻は30日以内に設定してください")
        scheduled_utc_iso = sched_utc.isoformat()

    if body.segment:
        recipients = mbr.get_members_by_segment(body.segment)
    elif body.nft_types:
        recipients = []
        seen_emails = set()
        for nft_type in body.nft_types:
            for m in mbr.get_members_by_nft_type(nft_type):
                if m["email"] not in seen_emails:
                    seen_emails.add(m["email"])
                    recipients.append(m)
    else:
        if not body.confirm_all:
            raise HTTPException(
                status_code=400,
                detail="全員送信には confirm_all=true が必要です",
            )
        recipients = mbr.get_all_members()

    if not recipients:
        raise HTTPException(status_code=400, detail="送信先メンバーが見つかりません")

    # Gmail エイリアス（+タグ・ドット違い）が DB に複数登録されていても、
    # 同じ物理受信箱には 1 通しか届かないようにする。
    before_count = len(recipients)
    recipients = mbr.dedupe_by_inbox(recipients)
    after_count = len(recipients)
    if before_count != after_count:
        log.info(
            "Bulk send dedup by inbox: %d -> %d (skipped %d alias duplicates)",
            before_count, after_count, before_count - after_count,
        )

    job_id = db.create_bulk_job(
        subject=body.subject,
        body=body.body,
        nft_types=json.dumps(body.nft_types, ensure_ascii=False),
        total=len(recipients),
        scheduled_at=scheduled_utc_iso,
        segment=body.segment,
        confirm_all=body.confirm_all,
        recipients=recipients,
    )

    # 予約ジョブは DB 登録のみ。実際の送信は cron worker が時刻到達時に行う。
    if scheduled_utc_iso:
        return {
            "status": "scheduled",
            "job_id": job_id,
            "count": len(recipients),
            "scheduled_at": scheduled_utc_iso,
        }

    def _on_result(member: dict, status: str, entry: dict):
        if status == "sent":
            db.record_sent_email(
                recipient_email=member["email"],
                recipient_name=member.get("name", ""),
                nft_type=member.get("nft_type", ""),
                subject=body.subject,
                body=entry.get("body", body.body),
                resend_id=entry.get("id"),
                bulk_job_id=job_id,
                status="sent",
            )
            db.increment_bulk_job(job_id, sent_delta=1)
        else:
            db.record_sent_email(
                recipient_email=member["email"],
                recipient_name=member.get("name", ""),
                nft_type=member.get("nft_type", ""),
                subject=body.subject,
                body=entry.get("body", body.body),
                bulk_job_id=job_id,
                status="error",
                error=entry.get("error", ""),
            )
            db.increment_bulk_job(job_id, failed_delta=1)

    def do_send():
        try:
            mail.send_bulk_emails(recipients, body.subject, body.body, on_result=_on_result)
        finally:
            db.finish_bulk_job(job_id)

    bg.add_task(do_send)
    return {"status": "started", "job_id": job_id, "count": len(recipients)}


@app.post("/api/send/jobs/{job_id}/cancel")
async def api_cancel_scheduled_job(
    job_id: int,
    _user: str = Depends(require_admin),
):
    if not db.cancel_scheduled_job(job_id):
        raise HTTPException(
            status_code=400,
            detail="このジョブはキャンセルできません（実行中・完了済・既にキャンセル済の可能性）",
        )
    return {"status": "cancelled", "job_id": job_id}


@app.get("/api/send/jobs")
async def api_list_jobs(_user: str = Depends(require_admin)):
    return db.list_bulk_jobs()


@app.get("/api/send/jobs/{job_id}")
async def api_get_job(job_id: int, _user: str = Depends(require_admin)):
    job = db.get_bulk_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    return job


# ── 履歴 ────────────────────────────────────────────────
@app.get("/api/emails/sent")
async def api_sent_emails(
    limit: int = 50, offset: int = 0, search: str = "",
    bulk: str = "exclude",  # exclude | only | include
    _user: str = Depends(require_admin),
):
    if bulk not in ("exclude", "only", "include"):
        bulk = "exclude"
    return {
        "items": db.get_sent_emails(limit=limit, offset=offset, search=search, bulk=bulk),
        "total": db.count_sent_emails(search=search, bulk=bulk),
    }


@app.get("/api/emails/received")
async def api_received_emails(
    limit: int = 50, offset: int = 0, search: str = "",
    _user: str = Depends(require_admin),
):
    return {
        "items": db.get_received_emails(limit=limit, offset=offset, search=search),
        "total": db.count_received_emails(search=search),
    }


# ── NFT種別 ─────────────────────────────────────────────
@app.get("/api/nft-types")
async def api_nft_types(_user: str = Depends(require_admin)):
    return NFT_TYPES


# ── 承認 ────────────────────────────────────────────────
@app.get("/api/approvals")
async def api_list_approvals(_user: str = Depends(require_admin)):
    return db.list_pending_approvals()


@app.get("/api/approvals/{approval_id}")
async def api_get_approval(approval_id: int, _user: str = Depends(require_admin)):
    a = db.get_pending_approval(approval_id)
    if not a:
        raise HTTPException(status_code=404, detail="承認データが見つかりません")
    return a


class ApprovalAction(BaseModel):
    body: Optional[str] = None  # edit時の本文


@app.post("/api/approvals/{approval_id}/approve")
async def api_approve(approval_id: int, body: ApprovalAction, user: str = Depends(require_admin)):
    return _process_approval(approval_id, "approve", body.body, user)


@app.post("/api/approvals/{approval_id}/edit")
async def api_edit(approval_id: int, body: ApprovalAction, user: str = Depends(require_admin)):
    if not body.body:
        raise HTTPException(status_code=400, detail="本文を指定してください")
    return _process_approval(approval_id, "edit", body.body, user)


@app.post("/api/approvals/{approval_id}/reject")
async def api_reject(approval_id: int, user: str = Depends(require_admin)):
    return _process_approval(approval_id, "reject", None, user)


def _process_approval(approval_id: int, action: str, body_override: Optional[str], user: str) -> dict:
    approval = db.get_pending_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="承認データが見つかりません")
    if approval["status"] != "waiting":
        raise HTTPException(status_code=409, detail=f"既に処理済み (status: {approval['status']})")
    if not db.claim_pending_approval(approval_id, handled_by=user):
        raise HTTPException(status_code=409, detail="同時処理のため承認に失敗しました。再読み込みしてください。")

    if action == "reject":
        db.update_approval_status(approval_id, "rejected", handled_by=user)
        return {"status": "rejected"}

    final_body = body_override if action == "edit" else approval["ai_draft"]
    try:
        mail.send_reply(
            to_email=approval["sender_email"],
            to_name=approval["sender_name"] or "",
            original_subject=approval["original_subject"] or "",
            body=final_body,
            in_reply_to_message_id=approval.get("original_message_id"),
        )
    except mail.TestModeBlockedError as e:
        db.release_pending_approval(approval_id)
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        db.release_pending_approval(approval_id)
        log.exception("Approval send failure")
        raise HTTPException(status_code=500, detail=f"送信エラー: {e}")

    db.record_sent_email(
        recipient_email=approval["sender_email"],
        recipient_name=approval["sender_name"] or "",
        nft_type="",
        subject=f"Re: {approval['original_subject'] or ''}",
        body=final_body,
    )
    new_status = "approved_edited" if action == "edit" else "approved"
    db.update_approval_status(approval_id, new_status, handled_by=user)
    return {"status": new_status}


# ── テンプレート ────────────────────────────────────────
class TemplateUpsert(BaseModel):
    name: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


@app.get("/api/templates")
async def api_list_templates(_user: str = Depends(require_admin)):
    return db.list_templates()


@app.post("/api/templates")
async def api_upsert_template(body: TemplateUpsert, _user: str = Depends(require_admin)):
    tid = db.upsert_template(body.name, body.subject, body.body)
    return {"id": tid}


@app.delete("/api/templates/{template_id}")
async def api_delete_template(template_id: int, _user: str = Depends(require_admin)):
    if not db.delete_template(template_id):
        raise HTTPException(status_code=404, detail="テンプレートが見つかりません")
    return {"status": "deleted"}


# ── Resend Webhook ─────────────────────────────────────
@app.post("/webhook/email")
async def webhook_email(
    request: Request,
    bg: BackgroundTasks,
    _rl=Depends(limit_webhook),
):
    """Resend inbound email webhook。"""
    body_bytes = await verify_webhook_request(request)
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Resend の email.received webhook はメタデータのみ送信。本文を含むペイロードを
    # 受け取るには /emails/inbound/{email_id} を別途取得する必要がある。
    event_type = payload.get("type", "")
    data = payload.get("data", payload)
    sender_email = data.get("from") or data.get("sender") or ""
    sender_name = data.get("from_name") or data.get("sender_name") or ""
    subject = data.get("subject", "")
    body_text = data.get("text") or data.get("html") or data.get("body") or ""
    message_id = data.get("message_id") or ""
    in_reply_to = data.get("in_reply_to") or ""
    email_id = data.get("email_id") or data.get("id") or ""
    to_emails = _extract_email_list(data.get("to") or data.get("recipients") or [])
    if not _is_allowed_inbound_recipient(to_emails):
        log.info(
            "Webhook ignored: recipient domain not allowed to=%s allowed=%s",
            to_emails,
            RESEND_INBOUND_DOMAINS,
        )
        return {"status": "ignored", "reason": "recipient_domain_not_allowed"}

    if message_id and db.has_received_message_id(message_id):
        log.info("Webhook duplicate skipped by message_id=%s", message_id)
        return {"status": "duplicate"}
    if email_id and db.has_received_webhook_email_id(email_id):
        log.info("Webhook duplicate skipped by webhook_email_id=%s", email_id)
        return {"status": "duplicate"}

    # 本文が無い場合（email.received の webhook はメタデータのみ）、APIで取得
    if event_type == "email.received" and not body_text and email_id:
        try:
            import httpx
            from config import RESEND_API_KEY
            async with httpx.AsyncClient(timeout=10.0) as cli:
                r = await cli.get(
                    f"https://api.resend.com/inbound/emails/{email_id}",
                    headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                )
            if r.status_code == 200:
                full = r.json()
                body_text = full.get("text") or full.get("html") or ""
                if not to_emails:
                    to_emails = _extract_email_list(full.get("to") or full.get("recipients") or [])
                if not message_id:
                    message_id = full.get("message_id", "")
                log.info("Fetched inbound body: %d chars", len(body_text))
            else:
                log.error("Inbound fetch failed: HTTP %d %s url=https://api.resend.com/inbound/emails/%s", r.status_code, r.text[:200], email_id)
        except Exception:
            log.exception("Failed to fetch inbound email body")

    if not _is_allowed_inbound_recipient(to_emails):
        log.info(
            "Webhook ignored after hydrate: recipient domain not allowed to=%s allowed=%s",
            to_emails,
            RESEND_INBOUND_DOMAINS,
        )
        return {"status": "ignored", "reason": "recipient_domain_not_allowed"}

    # "from" が "Name <email@x>" 形式の場合の分解
    if "<" in sender_email and ">" in sender_email:
        import re as _re
        m = _re.match(r"\s*(.*?)\s*<([^>]+)>\s*", sender_email)
        if m:
            sender_name = sender_name or m.group(1).strip().strip('"')
            sender_email = m.group(2).strip()

    if not sender_email or not body_text:
        log.warning("Webhook ignored: missing sender or body (type=%s email_id=%s)", event_type, email_id)
        return JSONResponse({"status": "ignored"})
    if message_id and db.has_received_message_id(message_id):
        log.info("Webhook duplicate skipped after hydrate by message_id=%s", message_id)
        return {"status": "duplicate"}
    if email_id and db.has_received_webhook_email_id(email_id):
        log.info("Webhook duplicate skipped after hydrate by webhook_email_id=%s", email_id)
        return {"status": "duplicate"}

    def process():
        member = mbr.get_member_by_email(sender_email)
        is_member = member is not None
        nft_type = member["nft_type"] if member else "不明"

        history = db.get_recent_exchange(sender_email, limit=AI_HISTORY_DEPTH)
        purchase_summary = db.get_purchase_summary(sender_email) if is_member else None
        lucky_summary = db.get_lucky_dashboard(sender_email)

        try:
            result = ai.generate_reply(
                sender_name=sender_name,
                sender_email=sender_email,
                nft_type=nft_type,
                original_subject=subject,
                original_body=body_text,
                history=history,
                purchases=purchase_summary,
                is_member=is_member,
                lucky=lucky_summary,
            )
        except Exception as e:
            log.exception("AI generation failure")
            result = {
                "reply": "", "confidence": 0.0,
                "needs_human": True, "reason": f"AI生成エラー: {e}",
            }

        received_id, created = db.record_received_email_if_new(
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            body=body_text,
            ai_draft=result.get("reply", ""),
            ai_confidence=result.get("confidence"),
            message_id=message_id,
            webhook_email_id=email_id,
            in_reply_to=in_reply_to,
        )
        if not created:
            log.info("Webhook duplicate insert skipped for message_id=%s", message_id)
            return

        if result.get("needs_human"):
            approval_id = db.create_pending_approval(
                received_email_id=received_id,
                ai_draft=result.get("reply", ""),
            )
            msg_id = telegram_bot.send_notification_sync(
                approval_id=approval_id,
                sender_name=sender_name,
                sender_email=sender_email,
                original_subject=subject,
                original_body=body_text,
                ai_draft=result.get("reply", ""),
                reason=result.get("reason", ""),
            )
            if msg_id:
                db.update_approval_telegram_message(approval_id, msg_id)
        else:
            try:
                mail.send_reply(
                    to_email=sender_email,
                    to_name=sender_name,
                    original_subject=subject,
                    body=result["reply"],
                    in_reply_to_message_id=message_id,
                )
                db.record_sent_email(
                    recipient_email=sender_email,
                    recipient_name=sender_name,
                    nft_type=nft_type,
                    subject=f"Re: {subject}",
                    body=result["reply"],
                )
                db.update_received_status(received_id, "auto_sent")
            except Exception as e:
                log.exception("Auto reply send failure")
                approval_id = db.create_pending_approval(
                    received_email_id=received_id,
                    ai_draft=result.get("reply", ""),
                )
                msg_id = telegram_bot.send_notification_sync(
                    approval_id=approval_id,
                    sender_name=sender_name,
                    sender_email=sender_email,
                    original_subject=subject,
                    original_body=body_text,
                    ai_draft=result.get("reply", ""),
                    reason=f"自動送信エラー（要確認）: {e}",
                )
                if msg_id:
                    db.update_approval_telegram_message(approval_id, msg_id)

    bg.add_task(process)
    return {"status": "received"}


def _is_allowed_inbound_recipient(to_emails: list[str]) -> bool:
    """Return True when the inbound event belongs to this Betimail domain."""
    if not RESEND_INBOUND_DOMAINS:
        return True
    if not to_emails:
        log.warning("Webhook recipient missing; continuing allowed=%s", RESEND_INBOUND_DOMAINS)
        return True
    return any(
        email.rsplit("@", 1)[1].lower() in RESEND_INBOUND_DOMAINS
        for email in to_emails
        if "@" in email
    )


def _extract_email_list(value) -> list[str]:
    """Extract normalized email addresses from Resend recipient fields."""
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    addresses: list[str] = []
    for item in raw_items:
        if isinstance(item, str):
            parsed = getaddresses([item])
            addresses.extend(email.lower() for _, email in parsed if email)
        elif isinstance(item, dict):
            raw = item.get("email") or item.get("address") or item.get("value") or ""
            parsed = getaddresses([str(raw)])
            addresses.extend(email.lower() for _, email in parsed if email)
    return addresses


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
