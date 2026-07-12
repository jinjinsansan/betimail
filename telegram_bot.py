"""Telegram Bot による承認フロー。

Bot は専用スレッドで polling する。FastAPI 側から通知を送る場合は、
Bot のイベントループに run_coroutine_threadsafe で投げる。
"""
import asyncio
import re
import threading
import time
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
_bot_stop_event = threading.Event()


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
            InlineKeyboardButton("✏️ 直接編集", callback_data=f"edit:{approval_id}"),
        ],
        [
            InlineKeyboardButton("💬 AI と相談して修正", callback_data=f"chat:{approval_id}"),
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
        if not db.claim_pending_approval(approval_id, handled_by=user):
            await query.edit_message_text("⚠️ この依頼は他の操作と競合したため処理できませんでした。")
            return
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
        except mail.TestModeBlockedError as e:
            db.release_pending_approval(approval_id)
            log.warning("Test mode blocked: %s", e)
            await query.edit_message_text(
                f"🚫 TEST_MODE のため送信ブロック\n"
                f"宛先 {approval['sender_email']} は許可リスト外です。\n\n"
                f"本番運用に切り替えるには /opt/betimail/.env で\n"
                f"TEST_MODE=false にしてください。"
            )
        except Exception as e:
            db.release_pending_approval(approval_id)
            log.exception("Telegram approve send failure")
            await query.edit_message_text(f"❌ 送信エラー: {e}")

    elif action == "edit":
        context.chat_data["pending_edit"] = approval_id
        context.chat_data.pop("pending_chat", None)
        await query.edit_message_text(
            f"✏️ 直接編集モード (承認ID: {approval_id})\n"
            f"修正した返信文を次のメッセージで送ってください。\n"
            f"送信先: {approval['sender_email']}\n\n"
            f"━━━ 現在の下書き ━━━\n{approval['ai_draft']}"
        )

    elif action == "chat":
        # AI 相談モード: 自然言語で指示を送ると AI が下書きを再生成する
        context.chat_data["pending_chat"] = approval_id
        context.chat_data.pop("pending_edit", None)
        await query.edit_message_text(
            f"💬 AI 相談モード (承認ID: {approval_id})\n"
            f"次のメッセージで自然言語で指示を送ってください。例:\n"
            f"  • もう少し優しく書き直して\n"
            f"  • 短くまとめて\n"
            f"  • 感謝の言葉を増やして\n"
            f"  • 個別対応を強調して\n\n"
            f"送信先: {approval['sender_email']}\n"
            f"━━━ 現在の下書き ━━━\n{approval['ai_draft'][:600]}\n\n"
            f"終了するには /cancel を送信"
        )

    elif action == "reject":
        if not db.claim_pending_approval(approval_id, handled_by=user):
            await query.edit_message_text("⚠️ この依頼は他の操作と競合したため処理できませんでした。")
            return
        db.update_approval_status(approval_id, "rejected", handled_by=user)
        await query.edit_message_text(f"❌ 却下しました (ID: {approval_id})")


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed_chat(update.effective_chat.id):
        return

    text = (update.message.text or "").strip()

    # /cancel で相談・編集モード終了
    if text in ("/cancel", "/end", "/終了"):
        context.chat_data.pop("pending_edit", None)
        context.chat_data.pop("pending_chat", None)
        await update.message.reply_text("ℹ️ モードを終了しました。")
        return

    edit_id = context.chat_data.get("pending_edit")
    chat_id = context.chat_data.get("pending_chat")

    if edit_id is not None:
        await _process_direct_edit(update, context, edit_id, text)
        return

    if chat_id is not None:
        await _process_ai_chat(update, context, chat_id, text)
        return

    # 関連なきメッセージは無視


async def _process_direct_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, approval_id: int, body: str):
    """✏️ 直接編集モード: 入力テキストをそのまま送信本文として使う"""
    approval = db.get_pending_approval(approval_id)
    if not approval:
        await update.message.reply_text("⚠️ 承認データが見つかりません。")
        context.chat_data.pop("pending_edit", None)
        return
    if approval.get("status") != "waiting":
        await update.message.reply_text(f"⚠️ この依頼は既に処理済みです (status: {approval.get('status')})")
        context.chat_data.pop("pending_edit", None)
        return
    user = update.effective_user.username if update.effective_user else "telegram"
    if not db.claim_pending_approval(approval_id, handled_by=user):
        await update.message.reply_text("⚠️ 他の操作と競合したため送信できませんでした。")
        context.chat_data.pop("pending_edit", None)
        return
    try:
        mail.send_reply(
            to_email=approval["sender_email"],
            to_name=approval["sender_name"] or "",
            original_subject=approval["original_subject"] or "",
            body=body,
            in_reply_to_message_id=approval.get("original_message_id"),
        )
        db.record_sent_email(
            recipient_email=approval["sender_email"],
            recipient_name=approval["sender_name"] or "",
            nft_type="",
            subject=f"Re: {approval['original_subject'] or ''}",
            body=body,
        )
        db.update_approval_status(approval_id, "approved_edited", handled_by=user)
        await update.message.reply_text(
            f"✅ 修正版を送信しました\n宛先: {approval['sender_email']}"
        )
    except mail.TestModeBlockedError as e:
        db.release_pending_approval(approval_id)
        log.warning("Test mode blocked: %s", e)
        await update.message.reply_text(
            f"🚫 TEST_MODE のため送信ブロック\n"
            f"宛先 {approval['sender_email']} は許可リスト外です。\n"
            f"修正本文は破棄せず保持しています。"
        )
        # 編集モードを維持して再試行できるようにする
        return
    except Exception as e:
        db.release_pending_approval(approval_id)
        log.exception("Telegram edit send failure")
        await update.message.reply_text(f"❌ 送信エラー: {e}")
    finally:
        context.chat_data.pop("pending_edit", None)


async def _process_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, approval_id: int, instruction: str):
    """💬 AI 相談モード: 自然言語の指示を AI に渡して下書きを再生成する。"""
    approval = db.get_pending_approval(approval_id)
    if not approval:
        await update.message.reply_text("⚠️ 承認データが見つかりません。")
        context.chat_data.pop("pending_chat", None)
        return
    if approval.get("status") != "waiting":
        await update.message.reply_text(f"⚠️ この依頼は既に処理済みです (status: {approval.get('status')})")
        context.chat_data.pop("pending_chat", None)
        return

    sender_email = approval["sender_email"]
    sender_name = approval.get("sender_name") or ""

    # AI 再生成に必要なコンテキスト
    import members as mbr
    import ai
    member = mbr.get_member_by_email(sender_email)
    is_member = member is not None
    nft_type = member["nft_type"] if member else "不明"
    purchases = db.get_purchase_summary(sender_email) if is_member else None
    lucky = db.get_lucky_dashboard(sender_email)

    await update.message.reply_text(f"🤖 AI が指示「{instruction[:60]}」で書き直し中…")

    try:
        result = ai.regenerate_reply(
            original_subject=approval.get("original_subject") or "",
            original_body=approval.get("original_body") or "",
            previous_draft=approval.get("ai_draft") or "",
            instruction=instruction,
            sender_name=sender_name,
            sender_email=sender_email,
            nft_type=nft_type,
            purchases=purchases,
            is_member=is_member,
            lucky=lucky,
        )
    except Exception as e:
        log.exception("AI regenerate failure")
        await update.message.reply_text(f"❌ AI 再生成エラー: {e}")
        return

    new_draft = result.get("reply", "")
    if not new_draft:
        await update.message.reply_text("❌ AI 再生成が空でした")
        return

    # DB の下書きを書き換え
    db.update_approval_draft(approval_id, new_draft)

    # 新しい下書きをカード形式で返す（再度ボタン提示）
    text = (
        f"💬 AI が書き直しました (承認ID: {approval_id})\n"
        f"━━━ 新しい下書き ━━━\n{new_draft}\n\n"
        f"このまま OK なら ✅、さらに指示なら自然言語で送ってください。\n"
        f"終了は /cancel"
    )
    await update.message.reply_text(text, reply_markup=_build_keyboard(approval_id))


def build_application() -> Application:
    global _application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(_handle_callback))
    # コマンド (/cancel) も含めて受け取る
    app.add_handler(MessageHandler(filters.TEXT, _handle_message))
    _application = app
    return app


def _run_bot_in_thread():
    """別スレッドで Bot を起動。専用の event loop をモジュール変数に保存する。"""
    global _bot_loop, _application
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    with _bot_loop_lock:
        _bot_loop = loop
    while not _bot_stop_event.is_set():
        app = build_application()
        try:
            app.run_polling(stop_signals=None)
        except Exception:
            log.exception("Telegram bot crashed")
        finally:
            _application = None
        if not _bot_stop_event.is_set():
            log.warning("Telegram bot restarting in 5 seconds")
            time.sleep(5)
    with _bot_loop_lock:
        _bot_loop = None


def start_bot_thread() -> Optional[threading.Thread]:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set; bot disabled")
        return None
    if not TELEGRAM_CHAT_IDS:
        log.warning("TELEGRAM_CHAT_ID not set; bot will receive but cannot send notifications")
    _bot_stop_event.clear()
    thread = threading.Thread(target=_run_bot_in_thread, name="telegram-bot", daemon=True)
    thread.start()
    log.info("Telegram bot thread started")
    return thread


async def shutdown_bot() -> None:
    """Bot を停止する。

    run_polling() は bot 専用スレッドの専用イベントループ上で動いている。
    別ループ（uvicorn 側）から `await _application.stop()` を呼ぶと停止処理が
    そのループに紐付かず刺さり、lifespan の finally が無期限にブロックして
    uvicorn 自体が終了できなくなる（コンテナがゾンビ化し 502 が続く）。

    そこで停止シグナルは bot のループ上で `application.stop_running()` を
    実行して送り、ここでは待たずに即座に返す。bot スレッドは daemon なので、
    仮に停止しきれなくてもプロセス終了とともに確実に片付く。
    """
    _bot_stop_event.set()
    app = _application
    with _bot_loop_lock:
        loop = _bot_loop
    if app is not None and loop is not None and loop.is_running():
        try:
            # stop_running() は run_polling() を内側からほどく。別スレッドからは
            # call_soon_threadsafe で bot のループ上にスケジュールして呼ぶ。
            loop.call_soon_threadsafe(app.stop_running)
            log.info("Telegram bot stop signalled")
        except Exception:
            log.exception("Telegram bot shutdown signal failure")


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
