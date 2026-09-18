"""承認待ちのまま下書きが空になっている AI 返信を作り直す。

2026-05 に受信した問合せのうち 4 件は AI 生成が失敗し、空の承認カードが
Telegram に出たまま放置された（中身が無いので承認しようがなかった）。
そういう「空のまま滞留している承認」を拾い直すためのツール。

**このスクリプトはメールを送らない。** 下書きを書き直すだけで、送信するかどうかは
管理画面 / Telegram で人が判断する。

例:
  python tools/regenerate_pending_drafts.py --dry-run
  python tools/regenerate_pending_drafts.py
  python tools/regenerate_pending_drafts.py --id 8 --id 10
  python tools/regenerate_pending_drafts.py --include-nonempty   # 既存の下書きも作り直す
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai  # noqa: E402
import db  # noqa: E402
import members as mbr  # noqa: E402
from config import AI_HISTORY_DEPTH  # noqa: E402


def _context_for(approval: dict) -> dict:
    """webhook の process() と同じ文脈を組み立てる。"""
    sender_email = approval.get("sender_email") or ""
    member = mbr.get_member_by_email(sender_email)
    is_member = member is not None
    return dict(
        sender_name=approval.get("sender_name") or "",
        sender_email=sender_email,
        nft_type=member["nft_type"] if member else "不明",
        original_subject=approval.get("original_subject") or "",
        original_body=approval.get("original_body") or "",
        history=db.get_recent_exchange(sender_email, limit=AI_HISTORY_DEPTH),
        purchases=db.get_purchase_summary(sender_email) if is_member else None,
        is_member=is_member,
        lucky=db.get_lucky_dashboard(sender_email),
        portal=db.get_portal_dashboard(sender_email),
        white=db.get_afi_dashboard(sender_email),
    )


def _mask(email: str) -> str:
    user, sep, domain = email.partition("@")
    return f"{user[:2]}***{sep}{domain}" if user else email


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--id", type=int, action="append", default=[], help="対象の approval id（複数可）")
    p.add_argument("--include-nonempty", action="store_true", help="下書きが既にあるものも作り直す")
    p.add_argument("--dry-run", action="store_true", help="DB を更新せず結果だけ表示")
    args = p.parse_args()

    targets = [a for a in db.list_pending_approvals(limit=200) if a.get("status") == "waiting"]
    if args.id:
        targets = [a for a in targets if a["id"] in args.id]
    if not args.include_nonempty:
        targets = [a for a in targets if not (a.get("ai_draft") or "").strip()]

    if not targets:
        print("対象なし（下書きが空の承認待ちはありません）")
        return 0

    print(f"対象 {len(targets)} 件" + ("（DRY-RUN）" if args.dry_run else ""))
    failures = 0
    for a in targets:
        label = f"id={a['id']} {_mask(a.get('sender_email') or '')} 「{(a.get('original_subject') or '')[:30]}」"
        if not (a.get("original_body") or "").strip():
            print(f"  - {label}: 元メール本文が空のためスキップ")
            failures += 1
            continue
        try:
            result = ai.generate_reply(**_context_for(a))
        except Exception as e:
            print(f"  ✗ {label}: 生成エラー {type(e).__name__}: {e}")
            failures += 1
            continue

        draft = (result.get("reply") or "").strip()
        if not draft:
            print(f"  ✗ {label}: 生成結果が空")
            failures += 1
            continue

        conf = result.get("confidence", 0.0)
        if args.dry_run:
            print(f"  ✓ {label}: {len(draft)}文字 conf={conf:.2f}（DRY-RUN・未保存）")
        else:
            db.update_approval_draft(a["id"], draft)
            print(f"  ✓ {label}: {len(draft)}文字 conf={conf:.2f} を保存")

    print(
        "完了。送信はしていません。"
        "管理画面の「承認」タブ、または Telegram の承認カードで内容を確認してください。"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
