"""指定した過去ジョブで失敗した宛先にだけ再送する。

使い方:
    docker exec betimail python /app/tools/retry_failed_bulk.py 2 --confirm
        # ジョブ #2 で status=error だった宛先にだけ、同じ件名・本文で再送

オプション:
    --confirm                 必須。これがないとドライランのみ
    --error-pattern STR       error カラムが STR を含む行だけを対象（デフォルト: rate限定）
    --interval-seconds 0.55   送信間隔（throttle 用）

新しい bulk_send_jobs 行を作成するため、履歴上は別ジョブとして残る。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("job_id", type=int, help="再送元のジョブID")
    p.add_argument("--confirm", action="store_true", help="本当に送信する")
    p.add_argument(
        "--error-pattern", default="Too many requests",
        help="この文字列を error に含む行だけを対象（既定: Resend rate limit）",
    )
    p.add_argument("--interval-seconds", type=float, default=None)
    args = p.parse_args()

    if args.interval_seconds is not None:
        os.environ["BULK_SEND_INTERVAL_SECONDS"] = str(args.interval_seconds)

    import db
    import mail

    src = db.get_bulk_job(args.job_id)
    if not src:
        print(f"job #{args.job_id} not found")
        sys.exit(1)

    # 失敗した宛先一覧を取得
    with db.get_conn() as c:
        rows = c.execute(
            """SELECT recipient_email AS email, recipient_name AS name, nft_type
               FROM sent_emails
               WHERE bulk_job_id = ?
                 AND status = 'error'
                 AND (error LIKE ?)""",
            (args.job_id, f"%{args.error_pattern}%"),
        ).fetchall()
    targets = [dict(r) for r in rows]

    print(f"=== retry source: job #{src['id']} ===")
    print(f"  subject: {src['subject']}")
    print(f"  total recipients matching error pattern: {len(targets)}")
    if not targets:
        print("nothing to retry")
        return
    print("  first 3 examples:")
    for t in targets[:3]:
        print(f"    - {t['email']}  ({t.get('name', '')})")

    if not args.confirm:
        print("\n--- DRY RUN. add --confirm to actually send ---")
        return

    print(f"\n=== creating new bulk job and resending {len(targets)} emails ===")
    new_id = db.create_bulk_job(
        subject=src["subject"],
        body=src["body"],
        nft_types=src.get("nft_types") or "[]",
        total=len(targets),
        scheduled_at=None,
        segment=None,
        confirm_all=False,
    )
    print(f"new job id: #{new_id}")

    def _on_result(member, status, entry):
        if status == "sent":
            db.record_sent_email(
                recipient_email=member["email"],
                recipient_name=member.get("name", ""),
                nft_type=member.get("nft_type", ""),
                subject=src["subject"],
                body=entry.get("body", src["body"]),
                resend_id=entry.get("id"),
                bulk_job_id=new_id,
                status="sent",
            )
            db.increment_bulk_job(new_id, sent_delta=1)
        else:
            db.record_sent_email(
                recipient_email=member["email"],
                recipient_name=member.get("name", ""),
                nft_type=member.get("nft_type", ""),
                subject=src["subject"],
                body=entry.get("body", src["body"]),
                bulk_job_id=new_id,
                status="error",
                error=entry.get("error", ""),
            )
            db.increment_bulk_job(new_id, failed_delta=1)

    try:
        mail.send_bulk_emails(targets, src["subject"], src["body"], on_result=_on_result)
    finally:
        db.finish_bulk_job(new_id)
        fresh = db.get_bulk_job(new_id)
        print(f"finished: sent={fresh['sent']} failed={fresh['failed']} / {fresh['total']}")


if __name__ == "__main__":
    main()
