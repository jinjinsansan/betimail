import db


def test_record_and_get_sent_email():
    rid = db.record_sent_email(
        recipient_email="a@example.com", recipient_name="A",
        nft_type="会員権NFT", subject="hi", body="body",
        resend_id="r1",
    )
    assert rid > 0
    items = db.get_sent_emails()
    assert items[0]["recipient_email"] == "a@example.com"
    assert items[0]["resend_id"] == "r1"


def test_received_and_approval_flow():
    rid = db.record_received_email(
        sender_email="x@example.com", sender_name="X",
        subject="?", body="hello", ai_draft="draft", ai_confidence=0.5,
        message_id="<m@x>",
    )
    aid = db.create_pending_approval(received_email_id=rid, ai_draft="draft")
    a = db.get_pending_approval(aid)
    assert a["sender_email"] == "x@example.com"
    assert a["original_message_id"] == "<m@x>"
    assert a["status"] == "waiting"

    pending = db.list_pending_approvals()
    assert len(pending) == 1

    db.update_approval_status(aid, "approved", handled_by="me")
    assert db.list_pending_approvals() == []
    assert db.get_pending_approval(aid)["status"] == "approved"


def test_bulk_job_lifecycle():
    job_id = db.create_bulk_job(subject="s", body="b", nft_types="[]", total=3)
    db.increment_bulk_job(job_id, sent_delta=2)
    db.increment_bulk_job(job_id, failed_delta=1)
    job = db.get_bulk_job(job_id)
    assert job["sent"] == 2 and job["failed"] == 1
    db.finish_bulk_job(job_id)
    assert db.get_bulk_job(job_id)["status"] == "done"


def test_search_pagination():
    for i in range(7):
        db.record_sent_email("u" + str(i) + "@x", "U" + str(i), "会員権NFT", f"件名{i}", "b")
    assert db.count_sent_emails() == 7
    page = db.get_sent_emails(limit=3, offset=0)
    assert len(page) == 3
    page2 = db.get_sent_emails(limit=3, offset=3)
    assert len(page2) == 3
    hits = db.get_sent_emails(search="件名1")
    assert len(hits) == 1


def test_templates_upsert_delete():
    tid = db.upsert_template("t1", "subj", "body")
    assert tid > 0
    db.upsert_template("t1", "subj2", "body2")  # update
    items = db.list_templates()
    assert len(items) == 1
    assert items[0]["subject"] == "subj2"
    assert db.delete_template(tid) is True
    assert db.list_templates() == []


def test_get_recent_exchange_ordering():
    db.record_received_email("x@y", "X", "1st", "hello 1")
    db.record_sent_email("x@y", "X", "", "re: 1st", "reply 1")
    db.record_received_email("x@y", "X", "2nd", "hello 2")
    history = db.get_recent_exchange("x@y", limit=5)
    # 時系列順 (古い→新しい)
    bodies = [h["body"] for h in history]
    assert bodies == ["hello 1", "reply 1", "hello 2"]


def test_scheduled_job_lifecycle():
    from datetime import datetime, timedelta, timezone
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    # 未来のジョブを作成（scheduled になる）
    future_id = db.create_bulk_job(
        subject="future", body="b", nft_types="[]", total=3,
        scheduled_at=future, segment=None, confirm_all=True,
    )
    assert db.get_bulk_job(future_id)["status"] == "scheduled"
    # 過去のジョブを作成（claim 対象）
    past_id = db.create_bulk_job(
        subject="past", body="b", nft_types="[]", total=2,
        scheduled_at=past, segment=None, confirm_all=True,
    )

    # claim_due_scheduled_jobs は past のみ取得し running に遷移
    now_iso = datetime.now(timezone.utc).isoformat()
    claimed = db.claim_due_scheduled_jobs(now_iso)
    claimed_ids = [j["id"] for j in claimed]
    assert past_id in claimed_ids
    assert future_id not in claimed_ids
    assert db.get_bulk_job(past_id)["status"] == "running"
    assert db.get_bulk_job(future_id)["status"] == "scheduled"

    # 重複 claim はされない (再呼び出しで past は出てこない)
    again = db.claim_due_scheduled_jobs(now_iso)
    assert past_id not in [j["id"] for j in again]


def test_cancel_scheduled_job():
    from datetime import datetime, timedelta, timezone
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    jid = db.create_bulk_job(
        subject="s", body="b", nft_types="[]", total=1,
        scheduled_at=future, segment=None, confirm_all=True,
    )
    assert db.cancel_scheduled_job(jid) is True
    assert db.get_bulk_job(jid)["status"] == "cancelled"
    # 再キャンセルは失敗
    assert db.cancel_scheduled_job(jid) is False
    # 通常 (running) ジョブはキャンセル不可
    running_id = db.create_bulk_job(subject="r", body="b", nft_types="[]", total=1)
    assert db.cancel_scheduled_job(running_id) is False


def test_received_email_dedup_with_webhook_email_id():
    rid1, created1 = db.record_received_email_if_new(
        sender_email="x@example.com",
        sender_name="X",
        subject="s",
        body="b",
        message_id="",
        webhook_email_id="email_123",
    )
    rid2, created2 = db.record_received_email_if_new(
        sender_email="x@example.com",
        sender_name="X",
        subject="s",
        body="b",
        message_id="",
        webhook_email_id="email_123",
    )
    assert created1 is True
    assert created2 is False
    assert rid1 == rid2
