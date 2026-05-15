"""FastAPI エントリポイント。"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date
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
    PUBLIC_CHECK_EXPOSE_DETAILS,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if not admin_configured():
        log.warning("ADMIN_PASSWORD が未設定です。管理画面はパブリックアクセス可能になっています。")
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


@app.post("/api/public/check")
async def api_public_check(
    body: PublicCheckRequest,
    request: Request,
    _rl=Depends(limit_public_check),
):
    """メルマガ配信対象者かどうかをユーザー自身が確認できる公開API。

    レート制限あり (20回/分/IP)。返却内容は本人特定可能だが、
    既に閉じたコミュニティ内の保有情報のため、emailを知っている人にのみ
    意味のある情報。Telegram/メール送信機能は提供しない。
    """
    member = mbr.get_member_by_email(body.email)
    if not member:
        return {"found": False}

    summary = db.get_purchase_summary(member["email"])
    nft_types = []
    for row in summary.get("by_nft", []):
        nft_types.append(row["nft_type"])

    # 重複除去・並び固定
    ordered = []
    for t in NFT_TYPES:
        if t in nft_types and t not in ordered:
            ordered.append(t)

    data = {"found": True}
    if PUBLIC_CHECK_EXPOSE_DETAILS:
        data["name"] = member["name"]
        data["nft_types"] = ordered
    return data


# ── 認証 ────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def api_login(
    body: LoginRequest,
    request: Request,
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
    _user: str = Depends(require_admin),
):
    items = db.list_withdraws(limit=limit, email=email)
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
async def api_withdraw_stats(_user: str = Depends(require_admin)):
    """ダッシュボード用の集計のみ。"""
    items = db.list_withdraws(limit=10000)
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


@app.post("/api/send")
async def api_send_email(
    body: SendEmailRequest,
    bg: BackgroundTasks,
    request: Request,
    _rl=Depends(limit_send),
    _user: str = Depends(require_admin),
):
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

    job_id = db.create_bulk_job(
        subject=body.subject,
        body=body.body,
        nft_types=json.dumps(body.nft_types, ensure_ascii=False),
        total=len(recipients),
    )

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
    _user: str = Depends(require_admin),
):
    return {
        "items": db.get_sent_emails(limit=limit, offset=offset, search=search),
        "total": db.count_sent_emails(search=search),
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
    message_id = data.get("message_id") or data.get("id") or ""
    in_reply_to = data.get("in_reply_to") or ""
    email_id = data.get("email_id") or data.get("id") or ""
    if message_id and db.has_received_message_id(message_id):
        log.info("Webhook duplicate skipped by message_id=%s", message_id)
        return {"status": "duplicate"}

    # 本文が無い場合（email.received の webhook はメタデータのみ）、APIで取得
    if event_type == "email.received" and not body_text and email_id:
        try:
            import httpx
            from config import RESEND_API_KEY
            r = httpx.get(
                f"https://api.resend.com/emails/inbound/{email_id}",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                timeout=10.0,
            )
            if r.status_code == 200:
                full = r.json()
                body_text = full.get("text") or full.get("html") or ""
                if not message_id:
                    message_id = full.get("message_id", "")
                log.info("Fetched inbound body: %d chars", len(body_text))
            else:
                log.warning("Inbound fetch failed: HTTP %d %s", r.status_code, r.text[:200])
        except Exception:
            log.exception("Failed to fetch inbound email body")

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

    def process():
        member = mbr.get_member_by_email(sender_email)
        is_member = member is not None
        nft_type = member["nft_type"] if member else "不明"

        history = db.get_recent_exchange(sender_email, limit=AI_HISTORY_DEPTH)
        purchase_summary = db.get_purchase_summary(sender_email) if is_member else None

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
