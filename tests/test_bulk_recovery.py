"""再起動で中断した一括送信ジョブの回収 (PROJECT_STATE §18.2) のテスト。

2026-07-17、送信中にコンテナを再ビルドして 194/961 で送信が止まり、
status は running のまま残った。誰も気づかず、767 名が未送信のまま放置された。
起動時に必ず検出されること、そして送信済みの人を二度と巻き込まないことを守る。
"""
import db


def _make_job(subject="betiメルマガ通信", total=961, sent=194, status="running"):
    job_id = db.create_bulk_job(
        subject=subject, body="本文", nft_types="[]", total=total,
        scheduled_at=None, segment=None, confirm_all=False,
    )
    with db.get_conn() as c:
        c.execute(
            "UPDATE bulk_send_jobs SET sent = ?, status = ? WHERE id = ?",
            (sent, status, job_id),
        )
    return job_id


def test_running_job_is_marked_interrupted_on_startup():
    job_id = _make_job()

    jobs = db.mark_interrupted_bulk_jobs()

    assert [j["id"] for j in jobs] == [job_id]
    assert jobs[0]["sent"] == 194 and jobs[0]["total"] == 961
    assert db.get_bulk_job(job_id)["status"] == "interrupted"


def test_finished_and_scheduled_jobs_are_left_alone():
    done_id = _make_job(status="done", sent=961)
    scheduled_id = _make_job(status="scheduled", sent=0)

    assert db.mark_interrupted_bulk_jobs() == []

    assert db.get_bulk_job(done_id)["status"] == "done"
    assert db.get_bulk_job(scheduled_id)["status"] == "scheduled"


def test_second_startup_does_not_re_report():
    """再起動のたびに同じジョブを通知し直さないこと。"""
    _make_job()

    assert len(db.mark_interrupted_bulk_jobs()) == 1
    assert db.mark_interrupted_bulk_jobs() == []


def test_resume_targets_exclude_already_sent():
    """再開の唯一の根拠が差分なので、送信済みが混ざらないことを確かめる。"""
    job_id = _make_job(total=3, sent=1)
    with db.get_conn() as c:
        for email in ("a@example.com", "b@example.com", "c@example.com"):
            c.execute(
                "INSERT INTO bulk_job_targets (job_id, recipient_email, recipient_name,"
                " nft_type, created_at) VALUES (?,?,?,?,datetime('now'))",
                (job_id, email, "N", "会員権NFT"),
            )
    db.record_sent_email(
        recipient_email="A@Example.com",  # 大文字小文字が違っても同一人物
        recipient_name="N", nft_type="会員権NFT", subject="s", body="b",
        bulk_job_id=job_id, status="sent",
    )
    db.record_sent_email(
        recipient_email="b@example.com", recipient_name="N", nft_type="会員権NFT",
        subject="s", body="b", bulk_job_id=job_id, status="error", error="Too many requests",
    )

    with db.get_conn() as c:
        rows = c.execute(
            """SELECT t.recipient_email AS email
               FROM bulk_job_targets t
               WHERE t.job_id = ?
                 AND NOT EXISTS (
                     SELECT 1 FROM sent_emails s
                     WHERE s.bulk_job_id = t.job_id
                       AND lower(s.recipient_email) = lower(t.recipient_email)
                       AND s.status = 'sent'
                 )""",
            (job_id,),
        ).fetchall()

    missing = sorted(r["email"] for r in rows)
    # a は送信済みなので除外。b は失敗、c は未着手なので対象。
    assert missing == ["b@example.com", "c@example.com"]
