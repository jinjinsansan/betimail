"""過去ジョブの取りこぼしにだけ再送する。

2 つのモードがある:

1. 失敗した宛先への再送（既定）
    docker exec betimail python /app/tools/retry_failed_bulk.py 2 --confirm
        # ジョブ #2 で status=error だった宛先にだけ、同じ件名・本文で再送

2. 中断したジョブの再開（--resume-missing）
    docker exec betimail python /app/tools/retry_failed_bulk.py 12 --resume-missing --confirm
        # bulk_job_targets（送信開始時の宛先スナップショット）と
        # sent_emails の差分 = 一度も送られていない宛先にだけ送る

2 は、送信中にコンテナを再ビルドして送信スレッドが死んだ場合の復旧用
（2026-07-17 に 194/961 で中断した事故。PROJECT_STATE §18.2）。
起動時に running のまま残っていたジョブは interrupted に落として Telegram 通知されるので、
その通知を見たらこのモードで再開する。差分だけを送るため二重送信にはならない。

オプション:
    --confirm                 必須。これがないとドライランのみ
    --resume-missing          未送信の宛先を対象にする（既定は失敗した宛先）
    --error-pattern STR       error カラムが STR を含む行だけを対象（既定モードのみ）
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
        "--resume-missing", action="store_true",
        help="中断ジョブの再開: 一度も送信されていない宛先だけを対象にする",
    )
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

    with db.get_conn() as c:
        if args.resume_missing:
            # 送信開始時のスナップショットのうち、sent が 1 件も無い宛先だけ。
            # 二重送信を防ぐ唯一の根拠がこの差分なので、必ず sent_emails 側で確認する。
            rows = c.execute(
                """SELECT t.recipient_email AS email, t.recipient_name AS name, t.nft_type
                   FROM bulk_job_targets t
                   WHERE t.job_id = ?
                     AND NOT EXISTS (
                         SELECT 1 FROM sent_emails s
                         WHERE s.bulk_job_id = t.job_id
                           AND lower(s.recipient_email) = lower(t.recipient_email)
                           AND s.status = 'sent'
                     )""",
                (args.job_id,),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT recipient_email AS email, recipient_name AS name, nft_type
                   FROM sent_emails
                   WHERE bulk_job_id = ?
                     AND status = 'error'
                     AND (error LIKE ?)""",
                (args.job_id, f"%{args.error_pattern}%"),
            ).fetchall()
    targets = [dict(r) for r in rows]

    print(f"=== retry source: job #{src['id']} (status={src.get('status')}) ===")
    print(f"  subject: {src['subject']}")
    if args.resume_missing:
        snapshot = 0
        with db.get_conn() as c:
            snapshot = c.execute(
                "SELECT count(*) FROM bulk_job_targets WHERE job_id = ?", (args.job_id,)
            ).fetchone()[0]
        if not snapshot:
            print("  bulk_job_targets にスナップショットがありません（この時期のジョブは再開できません）")
            return
        print(f"  snapshot={snapshot} / already sent={snapshot - len(targets)} / missing={len(targets)}")
    else:
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
