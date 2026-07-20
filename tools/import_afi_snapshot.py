"""afi.irah.uk（白のダッシュボード）のスクレイピングスナップショットを
betimail の afi_members へ投入し、検証レポートを出す。

前提: scrape_afi.py で以下を取得済みであること
  <dir>/_afi_users_raw.json    ユーザーマスタ（balance / wallet_address 含む）
  <dir>/_afi_nft_raw.json      会員権NFT 購入履歴（packet = 口数）
  <dir>/_afi_device_raw.json   パチスロホイホイ デバイス（list_user 1エントリ = 1口）

⚠ 残高は afi のスナップショット値をそのまま採用し、投入後に会員別の
   完全一致検証を行う（1件でも不一致なら exit 1）。
   ビジネスモデル停止済みのため残高は凍結（仁氏確認 2026-07-20）。
   本番公開前に afi 側の出金受付を止めてから最終スナップショットを取り直すこと。

使い方:
  python tools/import_afi_snapshot.py --dir data/_afi_snapshot
  python tools/import_afi_snapshot.py --dir data/_afi_snapshot \
      --into-betimail --betimail-db data/betimail.db [--add-preview]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_snapshot(snap_dir: str):
    def _load(name):
        path = os.path.join(snap_dir, name)
        if not os.path.exists(path):
            print(f"❌ {path} が無い（先に scrape_afi.py を実行）", file=sys.stderr)
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return _load("_afi_users_raw.json"), _load("_afi_nft_raw.json"), _load("_afi_device_raw.json")


def build_members(users: list, nft_buys: list, devices: list, snapshot_at: str) -> tuple[list[dict], dict]:
    """スナップショットから afi_members 行を構築し、検証用の統計も返す。"""
    users_by_id = {int(u["id"]): u for u in users if u.get("id") is not None}
    email_of = {uid: (u.get("email") or "").strip().lower() for uid, u in users_by_id.items()}

    # 会員権NFT: packet 合計（user_id ベース）
    kaiin_units: dict[str, int] = defaultdict(int)
    for r in nft_buys:
        uid = r.get("user_id")
        if uid is None:
            continue
        em = email_of.get(int(uid), "")
        if em:
            kaiin_units[em] += int(r.get("packet") or 0)

    # ホイホイ: device.list_user の 1 エントリ = 1 口（email ベース）
    hoihoi_units: dict[str, int] = defaultdict(int)
    unmatched_lu = 0
    known_emails = {e for e in email_of.values() if e}
    for d in devices:
        for entry in (d.get("list_user") or []):
            em = (entry.get("email") or "").strip().lower()
            if not em:
                continue
            hoihoi_units[em] += 1
            if em not in known_emails:
                unmatched_lu += 1

    members = []
    seen = set()
    for uid, u in users_by_id.items():
        em = email_of.get(uid, "")
        if not em or em in seen:
            continue
        bal = float(u.get("balance") or 0)
        k = kaiin_units.get(em, 0)
        h = hoihoi_units.get(em, 0)
        # 投入対象 = 残高≠0 or 会員権 or ホイホイ を持つユーザー
        if abs(bal) < 0.005 and k == 0 and h == 0:
            continue
        seen.add(em)
        members.append({
            "email": em,
            "name": u.get("name", ""),
            "afi_user_id": uid,
            "wallet_address": u.get("wallet_address"),
            "balance": bal,
            "kaiin_units": k,
            "hoihoi_units": h,
            "source": "scrape",
            "snapshot_at": snapshot_at,
        })
    # ユーザーマスタに居ないが list_user に登場する email（デバイス枠のみの保有者）
    for em, h in hoihoi_units.items():
        if em not in seen and em not in known_emails:
            seen.add(em)
            members.append({
                "email": em, "name": "", "afi_user_id": None, "wallet_address": None,
                "balance": 0.0, "kaiin_units": 0, "hoihoi_units": h,
                "source": "scrape", "snapshot_at": snapshot_at,
            })

    stats = {
        "users_total": len(users),
        "members": len(members),
        "balance_pos": sum(1 for m in members if m["balance"] > 0),
        "balance_sum": sum(m["balance"] for m in members if m["balance"] > 0),
        "kaiin_holders": sum(1 for m in members if m["kaiin_units"] > 0),
        "kaiin_units": sum(m["kaiin_units"] for m in members),
        "hoihoi_holders": sum(1 for m in members if m["hoihoi_units"] > 0),
        "hoihoi_units": sum(m["hoihoi_units"] for m in members),
        "unmatched_list_user": unmatched_lu,
    }
    return members, stats


def report(stats: dict) -> None:
    print("\n" + "=" * 60)
    print("  白のダッシュボード スナップショット検証レポート")
    print("=" * 60)
    print(f"afi ユーザー総数: {stats['users_total']}")
    print(f"投入対象会員（残高 or 資産あり）: {stats['members']}")
    print(f"残高 > 0: {stats['balance_pos']} 名 / 合計 ${stats['balance_sum']:,.2f}")
    print(f"会員権NFT: {stats['kaiin_holders']} 名 / {stats['kaiin_units']} 口")
    print(f"ホイホイ: {stats['hoihoi_holders']} 名 / {stats['hoihoi_units']} 口")
    if stats["unmatched_list_user"]:
        print(f"⚠ ユーザーマスタに居ない list_user エントリ: {stats['unmatched_list_user']} 件（メール直登録で投入）")
    print("=" * 60)


def into_betimail(members: list[dict], betimail_db: str, add_preview: bool) -> None:
    os.environ["BETIMAIL_DB_PATH"] = os.path.abspath(betimail_db)
    import importlib
    import config as _config
    importlib.reload(_config)
    import db as _db
    importlib.reload(_db)
    _db.init_db()

    print(f"\n[投入] afi_members {len(members)} 件")
    _db.clear_afi_members()
    _db.bulk_upsert_afi_members(members)

    if add_preview:
        print("[投入] プレビュー会員 (goldbenchan@gmail.com, source='preview')")
        _db.bulk_upsert_afi_members([{
            "email": "goldbenchan@gmail.com", "name": "プレビュー管理者",
            "afi_user_id": None, "wallet_address": None,
            "balance": 88.88, "kaiin_units": 4, "hoihoi_units": 2,
            "source": "preview", "snapshot_at": datetime.now().isoformat(),
        }])

    # ── 残高・口数の完全一致検証 ──
    print("\n[検証] スナップショットとの会員別 完全一致チェック")
    mismatches = []
    for m in members:
        got = _db.get_afi_member(m["email"])
        if got is None:
            mismatches.append((m["email"], "missing"))
            continue
        if abs((got["balance"] or 0) - m["balance"]) >= 0.005:
            mismatches.append((m["email"], f"balance {m['balance']} != {got['balance']}"))
        if (got["kaiin_units"] or 0) != m["kaiin_units"] or (got["hoihoi_units"] or 0) != m["hoihoi_units"]:
            mismatches.append((m["email"], "units mismatch"))
    totals = _db.afi_totals()
    print(f"    betimail側: 会員 {totals['members']} 名 / 残高合計 ${totals['total_balance']:,.2f} "
          f"(残高>0 {totals['members_with_balance']} 名)")
    print(f"    会員権 {totals['total_kaiin_units']} 口 / ホイホイ {totals['total_hoihoi_units']} 口")
    if mismatches:
        print(f"    ❌ 不一致 {len(mismatches)} 件:")
        for e, why in mismatches[:20]:
            print(f"       {e}: {why}")
        sys.exit(1)
    print(f"    ✅ 全 {len(members)} 会員の残高・口数がスナップショットと完全一致")
    print(f"\n✅ betimail DB ({betimail_db}) 投入完了")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="data/_afi_snapshot", help="scrape_afi.py の出力ディレクトリ")
    p.add_argument("--snapshot-at", default=None, help="スナップショット日時（既定: ファイル更新日時）")
    p.add_argument("--into-betimail", action="store_true")
    p.add_argument("--betimail-db", default="data/betimail.db")
    p.add_argument("--add-preview", action="store_true",
                   help="プレビュー会員 (goldbenchan) を追加（ソフトローンチ動作確認用）")
    args = p.parse_args()

    users, nft_buys, devices = load_snapshot(args.dir)
    snapshot_at = args.snapshot_at or datetime.fromtimestamp(
        os.path.getmtime(os.path.join(args.dir, "_afi_users_raw.json"))
    ).isoformat()
    print(f"スナップショット: {args.dir} (取得日時 {snapshot_at[:19]})")

    members, stats = build_members(users, nft_buys, devices, snapshot_at)
    report(stats)

    if args.into_betimail:
        into_betimail(members, args.betimail_db, add_preview=args.add_preview)


if __name__ == "__main__":
    main()
