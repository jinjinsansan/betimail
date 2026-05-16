"""期限到達した予約配信ジョブを実行する。

cron から 1 分毎に呼ばれる想定:
    * * * * * docker exec betimail python /app/tools/run_scheduled_jobs.py >> /opt/betimail/logs/scheduler/run.log 2>&1
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = Path("/opt/betimail/logs/scheduler")
LOG_FILE = LOG_DIR / "run.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_KEEP = 5


def _rotate_log_file(path: Path, max_bytes: int = LOG_MAX_BYTES, keep: int = LOG_KEEP) -> None:
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    for i in range(keep - 1, 0, -1):
        src = path.with_name(f"{path.name}.{i}")
        dst = path.with_name(f"{path.name}.{i + 1}")
        if src.exists():
            src.replace(dst)
    path.replace(path.with_name(f"{path.name}.1"))


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _rotate_log_file(LOG_FILE)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def telegram_notify(text: str) -> None:
    """予約配信の開始・完了・失敗を Telegram に通知 (任意)。"""
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        import urllib.parse
        import urllib.request
        chat_id_first = chat_id.split(",")[0].strip()
        data = urllib.parse.urlencode({"chat_id": chat_id_first, "text": text}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10
        ).read()
    except Exception as e:
        log(f"telegram notify failed: {e}")


def _resolve_recipients(job: dict) -> list[dict]:
    import members as mbr

    segment = job.get("segment")
    confirm_all = bool(job.get("confirm_all"))
    nft_types_raw = job.get("nft_types") or "[]"
    try:
        nft_types = json.loads(nft_types_raw)
    except Exception:
        nft_types = []

    if segment:
        recipients = mbr.get_members_by_segment(segment)
    elif nft_types:
        recipients = []
        seen = set()
        for t in nft_types:
            for m in mbr.get_members_by_nft_type(t):
                if m["email"] not in seen:
                    seen.add(m["email"])
                    recipients.append(m)
    elif confirm_all:
        recipients = mbr.get_all_members()
    else:
        recipients = []

    return mbr.dedupe_by_inbox(recipients)


def _execute_job(job: dict) -> None:
    import db
    import mail

    job_id = int(job["id"])
    log(f"[#{job_id}] executing scheduled job (subject={job.get('subject')[:40]!r})")

    recipients = _resolve_recipients(job)
    if not recipients:
        log(f"[#{job_id}] no recipients - marking failed")
        db.increment_bulk_job(job_id, failed_delta=0)
        db.finish_bulk_job(job_id)
        telegram_notify(f"⚠️ 予約配信 #{job_id} 失敗: 送信先がありません")
        return

    def _on_result(member: dict, status: str, entry: dict) -> None:
        if status == "sent":
            db.record_sent_email(
                recipient_email=member["email"],
                recipient_name=member.get("name", ""),
                nft_type=member.get("nft_type", ""),
                subject=job["subject"],
                body=entry.get("body", job["body"]),
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
                subject=job["subject"],
                body=entry.get("body", job["body"]),
                bulk_job_id=job_id,
                status="error",
                error=entry.get("error", ""),
            )
            db.increment_bulk_job(job_id, failed_delta=1)

    try:
        mail.send_bulk_emails(recipients, job["subject"], job["body"], on_result=_on_result)
    finally:
        db.finish_bulk_job(job_id)
        fresh = db.get_bulk_job(job_id) or {}
        sent = fresh.get("sent", 0)
        failed = fresh.get("failed", 0)
        log(f"[#{job_id}] finished: sent={sent} failed={failed}")
        if failed > 0:
            telegram_notify(
                f"⚠️ 予約配信 #{job_id} 完了\n"
                f"件名: {job.get('subject', '')[:60]}\n"
                f"送信成功: {sent} / 失敗: {failed}"
            )
        else:
            telegram_notify(
                f"✅ 予約配信 #{job_id} 完了\n"
                f"件名: {job.get('subject', '')[:60]}\n"
                f"送信: {sent}通"
            )


def main() -> None:
    # /opt/betimail/.env を明示的に読み込む（cron は .env を読まない）
    env_file = Path("/opt/betimail/.env")
    if env_file.exists():
        import os
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    import db
    db.init_db()

    now_utc = datetime.now(timezone.utc).isoformat()
    jobs = db.claim_due_scheduled_jobs(now_utc)
    if not jobs:
        return  # サイレント終了 (1分毎なのでログを汚さない)

    log(f"claimed {len(jobs)} due scheduled job(s) at {now_utc}")
    for j in jobs:
        try:
            _execute_job(j)
        except Exception as e:
            log(f"[#{j['id']}] ERROR: {e}\n{traceback.format_exc()}")
            try:
                import db as _db
                _db.finish_bulk_job(j["id"])
            except Exception:
                pass
            telegram_notify(f"❌ 予約配信 #{j['id']} 実行エラー: {e}")


if __name__ == "__main__":
    main()
