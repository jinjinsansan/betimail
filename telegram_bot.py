"""Telegram Bot による承認フロー。

Bot は専用スレッドで polling する。FastAPI 側から通知を送る場合は、
Bot のイベントループに run_coroutine_threadsafe で投げる。
"""
import asyncio
import re
import threading
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, MessageHandler, filters, ContextTypes,
)

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS
from logging_config import get_logger
import db
import mail

log = get_logger(__name__)

# Bot 専用のイベントループ。run_polling 開始時にセットされる。
_bot_loop: Optional[asyncio.AbstractEventLoop] = None
_bot_loop_lock = threading.Lock()
_application: Optional[Application] = None


def _escape_md_v2(text: str) -> str:
    """MarkdownV2 で予約された記号をエスケープ。"""
    if not text:
        return ""
    # 全角はそのまま、半角の MarkdownV2 予約文字のみエスケープ
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", text)


def _format_notification(
    approval_id: int,
    sender_name: str,
    sender_email: str,
    original_subject: str,
    original_body: str,
    ai_draft: str,
    reason: str,
) -> str:
    def short(s: str, n: int = 800) -> str:
        s = s or ""
        return s if len(s) <= n else s[:n] + "…"

    parts = [
        f"📩 *新着メール返信依頼* \\(ID: {approval_id}\\)",
        "",
        f"*送信者:* {_escape_md_v2(sender_name or '不明')} \\({_escape_md_v2(sender_email)}\\)",
        f"*件名:* {_escape_md_v2(original_subject or '(なし)')}",
    ]
    if reason:
        parts.append(f"*確認理由:* {_escape_md_v2(reason)}")
    parts += [
        "",
        "━━━ 受信メール ━━━",
        _escape_md_v2(short(original_body)),
        "",
        "━━━ AIの下書き ━━━",
        _escape_md_v2(short(ai_draft)),
    ]
    return "\n".join(parts)


def _build_keyboard(approval_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 承認して送信", callback_data=f"approve:{approval_id}"),
            InlineKeyboardButton("✏️ 修正して送信", callback_data=f"edit:{approval_id}"),
        ],
        [
            InlineKeyboardButton("❌ 却下（返信しない）", callback_data=f"reject:{approval_id}"),
        ],
    ])


def _allowed_chat(chat_id) -> bool:
    if not TELEGRAM_CHAT_IDS:
        return False
    return str(chat_id) in TELEGRAM_CHAT_IDS


async def notify_approval_needed(
    approval_id: int,
    sender_name: str,
    sender_email: str,
    original_subject: str,
    original_body: str,
    ai_draft: str,
    reason: str = "",
) -> Optional[int]:
    """各 chat_id に通知。最後に成功した message_id を返す。"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        log.info("Telegram notification skipped: not configured")
        return None

    text = _format_notification(
        approval_id, sender_name, sender_email,
        original_subject, original_body, ai_draft, reason,
    )
    keyboard = _build_keyboard(approval_id)

    last_msg_id: Optional[int] = None
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
            last_msg_id = msg.message_id
            log.info("Telegram notified: chat_id=%s msg_id=%s", chat_id, last_msg_id)
        except Exception as e:
            log.exception("Telegram send failure to %s: %s", chat_id, e)
    return last_msg_id


# ── Callback / message handlers ─────────────────────────
async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _allowed_chat(update.effective_chat.id):
        await query.edit_message_text("⚠️ 許可されていないチャットです。")
        return

    try:
        action, approval_id_str = query.data.split(":", 1)
        approval_id = int(approval_id_str)
    except Exception:
        await query.edit_message_text("⚠️ 不正なコールバックデータです。")
        return

    approval = db.get_pending_approval(approval_id)
    if not approval:
        await query.edit_message_text("⚠️ 承認データが見つかりません。")
        return

    if approval["status"] != "waiting":
        await query.edit_message_text(f"⚠️ この依頼は既に処理済みです (status: {approval['status']})")
        return

    user = update.effective_user.username if update.effective_user else "telegram"

    if action == "approve":
        try:
            mail.send_reply(
                to_email=approval["sender_email"],
                to_name=approval["sender_name"] or "",
                original_subject=approval["original_subject"] or "",
                body=approval["ai_draft"],
                in_reply_to_message_id=approval.get("original_message_id"),
            )
            db.record_sent_email(
                recipient_email=approval["sender_email"],
                recipient_name=approval["sender_name"] or "",
                nft_type="",
                subject=f"Re: {approval['original_subject'] or ''}",
                body=approval["ai_draft"],
            )
            db.update_approval_status(approval_id, "approved", handled_by=user)
            await query.edit_message_text(
                f"✅ 送信完了\n宛先: {approval['sender_email']}"
            )
        except Exception as e:
            log.exception("Telegram approve send failure")
            await query.edit_message_text(f"❌ 送信エラー: {e}")

    elif action == "edit":
        context.chat_data["pending_edit"] = approval_id
        await query.edit_message_text(
            f"✏️ 修正モード (承認ID: {approval_id})\n"
            f"修正した返信文を次のメッセージで送ってください。\n"
            f"送信先: {approval['sender_email']}\n\n"
            f"━━━ 現在の下書き ━━━\n{approval['ai_draft']}"
        )

    elif action == "reject":
        db.update_approval_status(approval_id, "rejected", handled_by=user)
        await query.edit_message_text(f"❌ 却下しました (ID: {approval_id})")


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed_chat(update.effective_chat.id):
        return
    approval_id = context.chat_data.get("pending_edit")
    if approval_id is None:
        return

    approval = db.get_pending_approval(approval_id)
    if not approval:
        await update.message.reply_text("⚠️ 承認データが見つかりません。")
        context.chat_data.pop("pending_edit", None)
        return

    user = update.effective_user.username if update.effective_user else "telegram"
    edited_body = update.message.text
    try:
        mail.send_reply(
            to_email=approval["sender_email"],
            to_name=approval["sender_name"] or "",
            original_subject=approval["original_subject"] or "",
            body=edited_body,
            in_reply_to_message_id=approval.get("original_message_id"),
        )
        db.record_sent_email(
            recipient_email=approval["sender_email"],
            recipient_name=approval["sender_name"] or "",
            nft_type="",
            subject=f"Re: {approval['original_subject'] or ''}",
            body=edited_body,
        )
        db.update_approval_status(approval_id, "approved_edited", handled_by=user)
        await update.message.reply_text(
            f"✅ 修正版を送信しました\n宛先: {approval['sender_email']}"
        )
    except Exception as e:
        log.exception("Telegram edit send failure")
        await update.message.reply_text(f"❌ 送信エラー: {e}")
    finally:
        context.chat_data.pop("pending_edit", None)


def build_application() -> Application:
    global _application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(_handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    _application = app
    return app


def _run_bot_in_thread():
    """別スレッドで Bot を起動。専用の event loop をモジュール変数に保存する。"""
    global _bot_loop
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    with _bot_loop_lock:
        _bot_loop = loop
    app = build_application()
    try:
        app.run_polling(stop_signals=None)
    except Exception:
        log.exception("Telegram bot crashed")
    finally:
        with _bot_loop_lock:
            _bot_loop = None


def start_bot_thread() -> Optional[threading.Thread]:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set; bot disabled")
        return None
    if not TELEGRAM_CHAT_IDS:
        log.warning("TELEGRAM_CHAT_ID not set; bot will receive but cannot send notifications")
    thread = threading.Thread(target=_run_bot_in_thread, name="telegram-bot", daemon=True)
    thread.start()
    log.info("Telegram bot thread started")
    return thread


async def shutdown_bot() -> None:
    if _application is not None:
        try:
            await _application.stop()
            await _application.shutdown()
            log.info("Telegram bot stopped")
        except Exception:
            log.exception("Telegram bot shutdown failure")


def send_notification_sync(
    approval_id: int,
    sender_name: str,
    sender_email: str,
    original_subject: str,
    original_body: str,
    ai_draft: str,
    reason: str = "",
) -> Optional[int]:
    """同期コードから呼び出すための入口。Bot 専用ループに coroutine を投げる。

    Bot ループがまだ立ち上がっていなくても、最大数秒待ってリトライする。
    """
    if not TELEGRAM_BOT_TOKEN:
        return None

    coro = notify_approval_needed(
        approval_id, sender_name, sender_email,
        original_subject, original_body, ai_draft, reason,
    )

    # Bot ループに投げる
    import time
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        with _bot_loop_lock:
            loop = _bot_loop
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            try:
                return future.result(timeout=15.0)
            except Exception:
                log.exception("Telegram notification dispatch failure")
                return None
        time.sleep(0.1)

    # Bot ループが利用不可なら、その場で新規ループで送信（フォールバック）
    log.warning("Bot loop not available; sending notification with one-off loop")
    try:
        return asyncio.run(coro)
    except Exception:
        log.exception("One-off Telegram notification failure")
        return None
