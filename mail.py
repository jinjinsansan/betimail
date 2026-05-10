import resend
from config import RESEND_API_KEY, RESEND_FROM_EMAIL, RESEND_FROM_NAME

resend.api_key = RESEND_API_KEY


def send_email(to_email: str, to_name: str, subject: str, body: str) -> str:
    """メールを送信する。成功時は resend の email id を返す。"""
    params = resend.Emails.SendParams(
        from_=f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>",
        to=[f"{to_name} <{to_email}>"],
        subject=subject,
        html=body.replace("\n", "<br>"),
        text=body,
    )
    response = resend.Emails.send(params)
    return response["id"]


def send_bulk_emails(recipients: list[dict], subject: str, body_template: str) -> list[dict]:
    """
    recipients: [{"name": ..., "email": ..., "nft_type": ...}, ...]
    body_template: {name}, {nft_type} などのプレースホルダーを使用可
    """
    results = []
    for r in recipients:
        body = body_template.format(
            name=r.get("name", ""),
            nft_type=r.get("nft_type", ""),
            email=r.get("email", ""),
        )
        try:
            email_id = send_email(r["email"], r["name"], subject, body)
            results.append({"email": r["email"], "status": "sent", "id": email_id})
        except Exception as e:
            results.append({"email": r["email"], "status": "error", "error": str(e)})
    return results
