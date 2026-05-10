import asyncio
import threading
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

import db
import members as mbr
import mail
import ai
import telegram_bot
from config import NFT_TYPES, TELEGRAM_BOT_TOKEN


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # Telegram Botをバックグラウンドスレッドで起動
    if TELEGRAM_BOT_TOKEN:
        def run_bot():
            telegram_app = telegram_bot.build_application()
            telegram_app.run_polling(stop_signals=None)

        thread = threading.Thread(target=run_bot, daemon=True)
        thread.start()
    yield


app = FastAPI(title="Betimail - NFTコミュニティサポート", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


# ── 管理画面 ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── メンバーAPI ─────────────────────────────────────────
@app.get("/api/members")
async def api_get_members(nft_type: Optional[str] = None):
    if nft_type:
        return mbr.get_members_by_nft_type(nft_type)
    return mbr.get_all_members()


class MemberCreate(BaseModel):
    name: str
    email: str
    nft_type: str
    joined_date: str
    notes: str = ""


@app.post("/api/members")
async def api_add_member(body: MemberCreate):
    try:
        member = mbr.add_member(**body.model_dump())
        return member
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/members/{email:path}")
async def api_delete_member(email: str):
    ok = mbr.delete_member(email)
    if not ok:
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    return {"status": "deleted"}


# ── メール送信API ────────────────────────────────────────
class SendEmailRequest(BaseModel):
    nft_types: list[str] = []   # 空の場合は全員
    subject: str
    body: str


@app.post("/api/send")
async def api_send_email(body: SendEmailRequest, bg: BackgroundTasks):
    if body.nft_types:
        recipients = []
        for nft_type in body.nft_types:
            recipients.extend(mbr.get_members_by_nft_type(nft_type))
    else:
        recipients = mbr.get_all_members()

    if not recipients:
        raise HTTPException(status_code=400, detail="送信先メンバーが見つかりません")

    def do_send():
        results = mail.send_bulk_emails(recipients, body.subject, body.body)
        for r, member in zip(results, recipients):
            if r["status"] == "sent":
                db.record_sent_email(
                    recipient_email=member["email"],
                    recipient_name=member["name"],
                    nft_type=member["nft_type"],
                    subject=body.subject,
                    body=body.body.format(
                        name=member.get("name", ""),
                        nft_type=member.get("nft_type", ""),
                        email=member.get("email", ""),
                    ),
                )

    bg.add_task(do_send)
    return {"status": "sending", "count": len(recipients)}


# ── メール履歴API ────────────────────────────────────────
@app.get("/api/emails/sent")
async def api_sent_emails():
    return db.get_sent_emails()


@app.get("/api/emails/received")
async def api_received_emails():
    return db.get_received_emails()


# ── NFT種別一覧 ──────────────────────────────────────────
@app.get("/api/nft-types")
async def api_nft_types():
    return NFT_TYPES


# ── Resend Webhook（メール受信）─────────────────────────
@app.post("/webhook/email")
async def webhook_email(request: Request, bg: BackgroundTasks):
    """
    Resend の inbound email webhook を受け取る。
    Resend ダッシュボードで Inbound Routing の Webhook URL をこのエンドポイントに設定してください。
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Resend inbound email payload の主要フィールドを取得
    sender_email = payload.get("from", "")
    sender_name = payload.get("from_name", "")
    subject = payload.get("subject", "")
    body = payload.get("text", payload.get("html", ""))

    if not sender_email or not body:
        return JSONResponse({"status": "ignored"})

    def process():
        # 送信者がメンバーか確認
        member = mbr.get_member_by_email(sender_email)
        nft_type = member["nft_type"] if member else "不明"

        # AI返信生成
        try:
            result = ai.generate_reply(
                sender_name=sender_name,
                sender_email=sender_email,
                nft_type=nft_type,
                original_subject=subject,
                original_body=body,
            )
        except Exception as e:
            result = {
                "reply": "",
                "confidence": 0.0,
                "needs_human": True,
                "reason": f"AI生成エラー: {e}",
            }

        # DBに記録
        received_id = db.record_received_email(
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            body=body,
            ai_draft=result.get("reply", ""),
            ai_confidence=result.get("confidence"),
        )

        if result.get("needs_human"):
            # 管理者にTelegram通知（承認待ち）
            approval_id = db.create_pending_approval(
                received_email_id=received_id,
                ai_draft=result.get("reply", ""),
            )
            telegram_bot.send_notification_sync(
                approval_id=approval_id,
                sender_name=sender_name,
                sender_email=sender_email,
                original_subject=subject,
                original_body=body,
                ai_draft=result.get("reply", ""),
                reason=result.get("reason", ""),
            )
        else:
            # AIが自信を持って回答できる場合は自動送信
            try:
                mail.send_email(
                    to_email=sender_email,
                    to_name=sender_name,
                    subject=f"Re: {subject}",
                    body=result["reply"],
                )
                db.update_approval_status(
                    db.create_pending_approval(received_id, result["reply"]),
                    "auto_sent",
                )
            except Exception as e:
                # 送信失敗時はTelegram通知にフォールバック
                approval_id = db.create_pending_approval(
                    received_email_id=received_id,
                    ai_draft=result.get("reply", ""),
                )
                telegram_bot.send_notification_sync(
                    approval_id=approval_id,
                    sender_name=sender_name,
                    sender_email=sender_email,
                    original_subject=subject,
                    original_body=body,
                    ai_draft=result.get("reply", ""),
                    reason=f"自動送信エラー（要確認）: {e}",
                )

    bg.add_task(process)
    return {"status": "received"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
