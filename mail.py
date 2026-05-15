"""Resend SDK ラッパー。
SendParams は TypedDict なので **kwargs ではなく dict として渡す必要がある。
"""
import html as html_lib
import resend
from typing import Optional
from config import (
    RESEND_API_KEY, RESEND_FROM_EMAIL, RESEND_FROM_NAME,
    TEST_MODE, TEST_ALLOWED_RECIPIENTS,
)
from logging_config import get_logger

log = get_logger(__name__)

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


class TestModeBlockedError(RuntimeError):
    """TEST_MODE が有効で、宛先が許可リストに無い場合に発生。"""


def _ensure_recipient_allowed(to_email: str) -> None:
    if not TEST_MODE:
        return
    addr = (to_email or "").strip().lower()
    if addr not in TEST_ALLOWED_RECIPIENTS:
        log.warning(
            "🚫 TEST_MODE: blocked send to %s (allowed: %s)",
            to_email, TEST_ALLOWED_RECIPIENTS,
        )
        raise TestModeBlockedError(
            f"TEST_MODE のため {to_email} への送信は禁止されています。"
            f"許可アドレス: {', '.join(TEST_ALLOWED_RECIPIENTS) or '(なし)'}"
        )


def _addr(email: str, name: str) -> str:
    if name:
        return f"{name} <{email}>"
    return email


def _text_to_html(text: str) -> str:
    return html_lib.escape(text).replace("\n", "<br>")


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    headers: Optional[dict[str, str]] = None,
    reply_to: Optional[str] = None,
) -> str:
    """メール送信。成功時に resend の email id を返す。失敗時は例外。

    TEST_MODE=true の時、TEST_ALLOWED_RECIPIENTS 以外への送信は
    TestModeBlockedError を投げて拒否する。
    """
    _ensure_recipient_allowed(to_email)
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY が設定されていません")
    if not RESEND_FROM_EMAIL:
        raise RuntimeError("RESEND_FROM_EMAIL が設定されていません")

    params: dict = {
        "from": _addr(RESEND_FROM_EMAIL, RESEND_FROM_NAME),
        "to": [_addr(to_email, to_name)],
        "subject": subject,
        "html": _text_to_html(body),
        "text": body,
    }
    if headers:
        params["headers"] = headers
    if reply_to:
        params["reply_to"] = reply_to

    response = resend.Emails.send(params)
    email_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", "")
    log.info("Mail sent: id=%s to=%s subject=%r", email_id, to_email, subject)
    return email_id or ""


def send_reply(
    to_email: str,
    to_name: str,
    original_subject: str,
    body: str,
    in_reply_to_message_id: Optional[str] = None,
) -> str:
    """受信メールへの返信。In-Reply-To / References ヘッダでスレッドを維持。"""
    subject = original_subject or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    headers = {}
    if in_reply_to_message_id:
        # Message-ID は <id@host> 形式が標準
        mid = in_reply_to_message_id
        if not mid.startswith("<"):
            mid = f"<{mid}>"
        headers["In-Reply-To"] = mid
        headers["References"] = mid
    return send_email(to_email, to_name, subject, body, headers=headers or None)


def send_bulk_emails(
    recipients: list[dict],
    subject: str,
    body_template: str,
    on_result=None,
) -> list[dict]:
    """
    recipients: [{"name": ..., "email": ..., "nft_type": ...}, ...]
    body_template: {name}/{nft_type}/{email} プレースホルダ対応
    on_result(member, status, result_dict) コールバック（毎件呼ばれる）
    """
    results = []
    for r in recipients:
        try:
            body = body_template.format(
                name=r.get("name", ""),
                nft_type=r.get("nft_type", ""),
                email=r.get("email", ""),
            )
        except KeyError as e:
            err = f"テンプレートに未知のプレースホルダ {e} が含まれています"
            log.warning("Bulk send template error for %s: %s", r.get("email"), err)
            entry = {"email": r["email"], "status": "error", "error": err, "body": ""}
            results.append(entry)
            if on_result:
                on_result(r, "error", entry)
            continue

        try:
            email_id = send_email(r["email"], r.get("name", ""), subject, body)
            entry = {"email": r["email"], "status": "sent", "id": email_id, "body": body}
        except Exception as e:
            log.exception("Bulk send failure to %s", r.get("email"))
            entry = {"email": r["email"], "status": "error", "error": str(e), "body": body}
        results.append(entry)
        if on_result:
            on_result(r, entry["status"], entry)
    return results
