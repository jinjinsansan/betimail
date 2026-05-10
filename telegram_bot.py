import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import db
import mail

_bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None


async def notify_approval_needed(
    approval_id: int,
    sender_name: str,
    sender_email: str,
    original_subject: str,
    original_body: str,
    ai_draft: str,
    reason: str = "",
) -> int | None:
    """Telegramに承認依頼を送信する。返り値はTelegramのmessage_id。"""
    if not _bot:
        return None

    text = (
        f"📩 *新着メール返信依頼* (ID: {approval_id})\n\n"
        f"*送信者:* {sender_name or '不明'} ({sender_email})\n"
        f"*件名:* {original_subject or '(なし)'}\n"
        f"{'*確認理由:* ' + reason + chr(10) if reason else ''}\n"
        f"━━━ 受信メール ━━━\n{original_body[:800]}{'...' if len(original_body) > 800 else ''}\n\n"
        f"━━━ AIの下書き ━━━\n{ai_draft[:800]}{'...' if len(ai_draft) > 800 else ''}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 承認して送信", callback_data=f"approve:{approval_id}"),
            InlineKeyboardButton("✏️ 修正して送信", callback_data=f"edit:{approval_id}"),
        ],
        [
            InlineKeyboardButton("❌ 却下（返信しない）", callback_data=f"reject:{approval_id}"),
        ],
    ])

    msg = await _bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return msg.message_id


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    action, approval_id_str = data.split(":", 1)
    approval_id = int(approval_id_str)

    approval = db.get_pending_approval(approval_id)
    if not approval:
        await query.edit_message_text("⚠️ 承認データが見つかりません。")
        return

    if action == "approve":
        try:
            mail.send_email(
                to_email=approval["sender_email"],
                to_name=approval["sender_name"] or "",
                subject=f"Re: {approval['original_subject'] or ''}",
                body=approval["ai_draft"],
            )
            db.update_approval_status(approval_id, "approved")
            await query.edit_message_text(
                f"✅ 送信完了\n宛先: {approval['sender_email']}"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ 送信エラー: {e}")

    elif action == "edit":
        context.user_data[f"editing_{approval_id}"] = True
        await query.edit_message_text(
            f"✏️ *修正モード* (承認ID: {approval_id})\n\n"
            f"修正した返信文を次のメッセージで送ってください。\n"
            f"送信先: {approval['sender_email']}\n\n"
            f"━━━ 現在の下書き ━━━\n{approval['ai_draft']}",
            parse_mode="Markdown",
        )
        context.chat_data["pending_edit"] = approval_id

    elif action == "reject":
        db.update_approval_status(approval_id, "rejected")
        await query.edit_message_text(f"❌ 却下しました (ID: {approval_id})")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """修正テキストを受け取ってメール送信する。"""
    if str(update.effective_chat.id) != str(TELEGRAM_CHAT_ID):
        return

    approval_id = context.chat_data.get("pending_edit")
    if approval_id is None:
        return

    approval = db.get_pending_approval(approval_id)
    if not approval:
        await update.message.reply_text("⚠️ 承認データが見つかりません。")
        context.chat_data.pop("pending_edit", None)
        return

    edited_body = update.message.text
    try:
        mail.send_email(
            to_email=approval["sender_email"],
            to_name=approval["sender_name"] or "",
            subject=f"Re: {approval['original_subject'] or ''}",
            body=edited_body,
        )
        db.update_approval_status(approval_id, "approved_edited")
        await update.message.reply_text(
            f"✅ 修正版を送信しました\n宛先: {approval['sender_email']}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ 送信エラー: {e}")

    context.chat_data.pop("pending_edit", None)


def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


def send_notification_sync(
    approval_id: int,
    sender_name: str,
    sender_email: str,
    original_subject: str,
    original_body: str,
    ai_draft: str,
    reason: str = "",
) -> int | None:
    """同期コードから呼べるラッパー。"""
    if not TELEGRAM_BOT_TOKEN:
        return None
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.ensure_future(notify_approval_needed(
                approval_id, sender_name, sender_email,
                original_subject, original_body, ai_draft, reason
            ))
            return None
        else:
            return loop.run_until_complete(notify_approval_needed(
                approval_id, sender_name, sender_email,
                original_subject, original_body, ai_draft, reason
            ))
    except Exception:
        return None
