"""ポータルサイト（betiダッシュボード）の MySQL ダンプから、ポータル再構築に
必要なテーブルを抽出して作業用 SQLite に取り込み、突合検証レポートを出す。

旧ポータル (nftportal.site 系) がアクセス不可のため、ベトナム法人提供の SQL ダンプ
(dashboard_20260715.sql) を正本として betimail 内にポータルを再構築する。

⚠ 最重要要件: 全会員の残高を旧ポータルと $1 も違わず一致させる。
   残高の正本は user_point_setting.balance。検証レポートで台帳
   (balance_change_history) との会員別突合を行い、乖離を全件列挙する。

対象テーブル:
  users                          会員アカウント (email / role / mode)
  user_point_setting             現在残高 balance（残高の正本）
  buy_nft                        NFT 購入 (nft 種別 / quantity)
  staking_histories              ステーキング (number_nft_remain = 有効枚数 = 分配対象)
  commission_histories           報酬明細 (1入金=1行)
  reward_distribution_histories  分配イベント
  balance_change_history         残高変動台帳 (type 5007=報酬入金)
  request_withdraw               出金申請
  nft_change_history             NFT 増減台帳 (4002=transfer / 4003=stake / 4004=解除)
  user_wallet                    ウォレットアドレス（出金先の初期値）

使い方:
  python tools/import_dashboard_dump.py \
      --dump data/dashboard_20260715.sql \
      --out  data/_import/portal_work.db
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TARGET_TABLES = [
    "users",
    "user_point_setting",
    "buy_nft",
    "staking_histories",
    "commission_histories",
    "reward_distribution_histories",
    "balance_change_history",
    "request_withdraw",
    "nft_change_history",
    "user_wallet",
]

# dump の enum → betimail の NFT 名称
NFT_LABELS = {
    "MEMBER": "会員権NFT",
    "HOIHOI": "パチスロホイホイNFT",
    "SPECIAL_MUSTARD": "スペシャルマスタードNFT",
    "LUCKY_MUSTARD": "ラッキーマスタードNFT",
    "LEADER": "LEADER",
    "DIGITAL_PACHISURO": "DIGITAL_PACHISURO",
}

CREATE_RE = re.compile(r"^CREATE TABLE (?:IF NOT EXISTS )?`([^`]+)`")
COL_RE = re.compile(r"^\s+`([^`]+)`\s")
INSERT_PREFIX = "INSERT INTO `"


def extract_columns(dump_path: str) -> dict[str, list[str]]:
    """各 CREATE TABLE ブロックから列名を順序通りに抽出。"""
    cols: dict[str, list[str]] = {}
    cur: str | None = None
    with open(dump_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = CREATE_RE.match(line)
            if m:
                cur = m.group(1) if m.group(1) in TARGET_TABLES else None
                if cur:
                    cols[cur] = []
                continue
            if cur is None:
                continue
            if line.startswith(")"):
                cur = None
                continue
            cm = COL_RE.match(line)
            if cm:
                cols[cur].append(cm.group(1))
    return cols


def parse_values(body: str, start: int = 0):
    """`INSERT ... VALUES` の後ろの `(...),(...),...;` を行タプル列に分解する。

    MySQL の文字列リテラル (シングルクォート、\\ エスケープ) を尊重したステートマシン。
    タプルの外で `;` に到達したら終了（phpMyAdmin の複数行 INSERT に対応）。
    """
    rows: list[list] = []
    i, n = start, len(body)
    while i < n:
        if body[i] != "(":
            if body[i] == ";":
                break
            i += 1
            continue
        i += 1
        fields: list = []
        cur = []
        in_str = False
        while i < n:
            c = body[i]
            if in_str:
                if c == "\\":
                    if i + 1 < n:
                        nxt = body[i + 1]
                        cur.append({"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(nxt, nxt))
                        i += 2
                        continue
                    i += 1
                    continue
                if c == "'":
                    if i + 1 < n and body[i + 1] == "'":
                        cur.append("'")
                        i += 2
                        continue
                    in_str = False
                    i += 1
                    continue
                cur.append(c)
                i += 1
                continue
            if c == "'":
                in_str = True
                cur = []
                fields.append(("str_pending", cur))
                i += 1
                continue
            if c in ",)":
                if fields and isinstance(fields[-1], tuple) and fields[-1][0] == "str_pending":
                    fields[-1] = "".join(fields[-1][1])
                else:
                    tok = "".join(cur).strip()
                    cur = []
                    if tok != "" or c == ",":
                        fields.append(_coerce(tok))
                if c == ")":
                    rows.append([f if not isinstance(f, tuple) else "".join(f[1]) for f in fields])
                    i += 1
                    break
                cur = []
                i += 1
                continue
            cur.append(c)
            i += 1
    return rows


def _coerce(tok: str):
    if tok == "" or tok.upper() == "NULL":
        return None
    try:
        if re.fullmatch(r"-?\d+", tok):
            return int(tok)
        return float(tok)
    except ValueError:
        return tok


def load_dump(dump_path: str, out_db: str) -> None:
    print(f"[1] 列定義を抽出: {dump_path}")
    cols = extract_columns(dump_path)
    for t in TARGET_TABLES:
        if t not in cols:
            print(f"    ⚠ テーブル {t} が見つからない")
        else:
            print(f"    {t}: {len(cols[t])} 列")

    os.makedirs(os.path.dirname(out_db) or ".", exist_ok=True)
    if os.path.exists(out_db):
        os.remove(out_db)
    conn = sqlite3.connect(out_db)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")

    for t in TARGET_TABLES:
        if t in cols:
            collist = ", ".join(f'"{c}"' for c in cols[t])
            conn.execute(f'CREATE TABLE "{t}" ({collist})')
    conn.commit()

    print("[2] INSERT 文を解析して取り込み (phpMyAdmin 形式)")
    counts: dict[str, int] = {t: 0 for t in TARGET_TABLES}
    with open(dump_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    for m in re.finditer(r"INSERT INTO `(\w+)` \(([^)]*)\) VALUES", text):
        table = m.group(1)
        if table not in TARGET_TABLES:
            continue
        insert_cols = [c.strip().strip("`") for c in m.group(2).split(",")]
        rows = parse_values(text, m.end())
        ncol = len(insert_cols)
        good = [r for r in rows if len(r) == ncol]
        if len(good) != len(rows):
            print(f"    ⚠ {table}: {len(rows)-len(good)}/{len(rows)} 行が列数不一致でスキップ")
        collist = ", ".join(f'"{c}"' for c in insert_cols)
        ph = ", ".join("?" * ncol)
        conn.executemany(f'INSERT INTO "{table}" ({collist}) VALUES ({ph})', good)
        counts[table] += len(good)
    conn.commit()
    for t in TARGET_TABLES:
        print(f"    {t}: {counts[t]} 行")
    conn.close()
    print(f"[3] 作業用 DB を書き出し: {out_db}")


def report(out_db: str, betimail_db: str | None) -> None:
    conn = sqlite3.connect(out_db)
    conn.row_factory = sqlite3.Row
    q = lambda s, *a: conn.execute(s, a).fetchall()  # noqa: E731
    one = lambda s, *a: conn.execute(s, a).fetchone()[0]  # noqa: E731

    print("\n" + "=" * 64)
    print("  突合検証レポート (ポータル dashboard_20260715)")
    print("=" * 64)

    # --- 会員 ---
    total_users = one("SELECT COUNT(*) FROM users")
    admins = one("SELECT COUNT(*) FROM users WHERE role=10")
    uniq_email = one("SELECT COUNT(DISTINCT lower(trim(email))) FROM users WHERE email IS NOT NULL AND email<>''")
    buyers = one("SELECT COUNT(DISTINCT user_id) FROM buy_nft")
    print(f"\n会員(users) 総数: {total_users}（email ユニーク {uniq_email} / role=10 管理者 {admins}）")
    print(f"購入実績のある会員 (buy_nft): {buyers} 名 → ポータル投入対象の母集団")

    # --- NFT 種別ごとの購入 ---
    print("\nNFT別 購入 (buy_nft):")
    print(f"  {'NFT':22s} {'購入者':>6s} {'総口数':>8s} {'購入額計':>14s}")
    for r in q("""SELECT nft, COUNT(DISTINCT user_id) c, SUM(quantity) u, SUM(amount) a
                  FROM buy_nft GROUP BY nft ORDER BY u DESC"""):
        print(f"  {r['nft']:22s} {r['c']:6d} {int(r['u'] or 0):8d} {float(r['a'] or 0):14,.2f}")

    # --- ステーク (分配対象口数 = 最新 number_nft_remain per user×nft) ---
    conn.execute("""
        CREATE TEMP VIEW latest_stake AS
        SELECT s.user_id, s.nft, s.number_nft_remain AS remain
        FROM staking_histories s
        JOIN (
            SELECT user_id, nft, MAX(id) AS mid
            FROM staking_histories GROUP BY user_id, nft
        ) m ON m.user_id = s.user_id AND m.nft = s.nft AND m.mid = s.id
    """)
    print("\nNFT別 有効ステーク (staking_histories 最新 number_nft_remain):")
    print(f"  {'NFT':22s} {'ステーカー':>6s} {'有効口数':>8s}")
    for r in q("""SELECT nft, COUNT(*) c, SUM(remain) u FROM latest_stake
                  WHERE remain > 0 GROUP BY nft ORDER BY u DESC"""):
        print(f"  {r['nft']:22s} {r['c']:6d} {int(r['u'] or 0):8d}")

    # 分配イベント側の total_nft_stake との比較（最後の分配時点）
    print("\n分配イベント (reward_distribution_histories):")
    for r in q("""SELECT nft, COUNT(*) c, MIN(time) mn, MAX(time) mx, SUM(amount) s
                  FROM reward_distribution_histories GROUP BY nft"""):
        last_stake = one("""SELECT total_nft_stake FROM reward_distribution_histories
                            WHERE nft=? ORDER BY time DESC LIMIT 1""", r["nft"])
        print(f"  {r['nft']:22s} 回数={r['c']:3d} 期間 {r['mn']}〜{r['mx']} 累計={float(r['s'] or 0):,.2f} 最終total_nft_stake={last_stake}")

    # --- 残高（最重要: user_point_setting が正本）---
    bal_cnt = one("SELECT COUNT(*) FROM user_point_setting WHERE balance > 0")
    bal_sum = one("SELECT COALESCE(SUM(balance),0) FROM user_point_setting WHERE balance > 0")
    bal_neg = one("SELECT COUNT(*) FROM user_point_setting WHERE balance < 0")
    print(f"\n残高 (user_point_setting.balance = 正本):")
    print(f"  残高 > 0: {bal_cnt} 名 / 合計 ${bal_sum:,.2f}")
    print(f"  残高 < 0: {bal_neg} 名")
    expect_cnt, expect_sum = 326, 35146.86
    ok = bal_cnt == expect_cnt and abs(bal_sum - expect_sum) < 0.005
    print(f"  期待値との一致 (326名 / $35,146.86): {'✅ 一致' if ok else '❌ 不一致 — 要調査'}")

    # 台帳との会員別検算: balance_change_history の最新残高 vs user_point_setting
    ledger: dict[int, tuple[int, float]] = {}
    for r in q("""SELECT id, from_id, to_id,
                         sender_balance_at_current_time sb,
                         receiver_balance_at_current_time rb
                  FROM balance_change_history ORDER BY id"""):
        if r["from_id"] is not None and r["sb"] is not None:
            ledger[r["from_id"]] = (r["id"], float(r["sb"]))
        if r["to_id"] is not None and r["rb"] is not None:
            ledger[r["to_id"]] = (r["id"], float(r["rb"]))
    mism = []
    for r in q("SELECT user_id, balance FROM user_point_setting"):
        uid, bal = r["user_id"], float(r["balance"] or 0)
        led = ledger.get(uid)
        if led is None:
            if abs(bal) >= 0.005:
                mism.append((uid, bal, None))
            continue
        if abs(bal - led[1]) >= 0.005:
            mism.append((uid, bal, led[1]))
    print(f"  台帳(balance_change_history)との会員別検算: 乖離 {len(mism)} 件")
    if mism:
        emails = {r["id"]: r["email"] for r in q("SELECT id, email FROM users")}
        print(f"    {'user_id':>8s} {'email':40s} {'正本balance':>12s} {'台帳残高':>12s}")
        for uid, bal, led in mism[:20]:
            led_s = f"{led:12,.2f}" if led is not None else "  (台帳なし)"
            print(f"    {uid:8d} {(emails.get(uid) or '?'):40s} {bal:12,.2f} {led_s}")
        if len(mism) > 20:
            print(f"    ... 他 {len(mism)-20} 件")
        print("    ※ 投入する残高は常に user_point_setting.balance（正本）を採用")

    # --- 報酬明細 ---
    print("\n報酬明細 (commission_histories):")
    for r in q("""SELECT nft, reward_type, COUNT(*) c, SUM(amount_commission) s
                  FROM commission_histories GROUP BY nft, reward_type"""):
        print(f"  {r['nft']:22s} {r['reward_type']:8s} {r['c']:6d} 件  計 ${float(r['s'] or 0):,.2f}")
    n5007 = one("SELECT COUNT(*) FROM balance_change_history WHERE type=5007")
    ncomm = one("SELECT COUNT(*) FROM commission_histories")
    print(f"  台帳 type=5007: {n5007} 件 / commission: {ncomm} 件 {'✅' if n5007 == ncomm else '⚠ 件数不一致'}")

    # --- 出金申請 ---
    print("\n出金申請 (request_withdraw):")
    for r in q("""SELECT status, COUNT(*) c, SUM(amount) s FROM request_withdraw GROUP BY status"""):
        label = {0: "申請中", 1: "処理中", 2: "完了", 3: "却下"}.get(r["status"], f"status={r['status']}")
        print(f"  {label:8s} {r['c']:3d} 件  計 ${float(r['s'] or 0):,.2f}")

    # --- NFT 台帳検算: staking vs nft_change_history ---
    print("\nNFT台帳検算 (nft_change_history):")
    for r in q("""SELECT nft, type, COUNT(*) c, SUM(amount) u FROM nft_change_history
                  GROUP BY nft, type ORDER BY nft, type"""):
        tlabel = {4002: "transfer", 4003: "stake", 4004: "stake解除"}.get(r["type"], str(r["type"]))
        print(f"  {r['nft']:22s} {tlabel:10s} {r['c']:5d} 件  {int(r['u'] or 0):8d} 口")

    # --- betimail purchases との email 突合 ---
    if betimail_db and os.path.exists(betimail_db):
        print(f"\nbetimail DB ({betimail_db}) purchases との email 突合:")
        b = sqlite3.connect(betimail_db)
        b.row_factory = sqlite3.Row
        dump_by_nft: dict[str, set[str]] = {}
        for r in q("""SELECT b.nft, lower(trim(u.email)) e
                      FROM buy_nft b JOIN users u ON u.id = b.user_id
                      WHERE u.email IS NOT NULL AND u.email <> ''"""):
            dump_by_nft.setdefault(r["nft"], set()).add(r["e"])
        beti_by_nft: dict[str, set[str]] = {}
        for r in b.execute("SELECT lower(trim(email)) e, nft_type FROM purchases"):
            for t in (r["nft_type"] or "").split(","):
                t = t.strip()
                if t:
                    beti_by_nft.setdefault(t, set()).add(r["e"])
        for enum_name, label in NFT_LABELS.items():
            d = dump_by_nft.get(enum_name, set())
            bt = beti_by_nft.get(label, set())
            if not d and not bt:
                continue
            only_d = d - bt
            only_b = bt - d
            print(f"  {enum_name:18s} dump {len(d):4d} / betimail {len(bt):4d}  共通 {len(d & bt):4d}  dumpのみ {len(only_d):4d}  betimailのみ {len(only_b):4d}")
        # 詳細リストをファイルに出力
        detail_path = os.path.join(os.path.dirname(out_db) or ".", "portal_email_diff.txt")
        with open(detail_path, "w", encoding="utf-8") as f:
            for enum_name, label in NFT_LABELS.items():
                d = dump_by_nft.get(enum_name, set())
                bt = beti_by_nft.get(label, set())
                if not d and not bt:
                    continue
                f.write(f"== {enum_name} ({label}) ==\n")
                f.write(f"-- dump のみ ({len(d - bt)}) --\n")
                for e in sorted(d - bt):
                    f.write(f"  {e}\n")
                f.write(f"-- betimail のみ ({len(bt - d)}) --\n")
                for e in sorted(bt - d):
                    f.write(f"  {e}\n")
        print(f"  詳細リスト: {detail_path}")
        b.close()
    else:
        print("\n(betimail DB 未指定/不存在: --betimail-db data/betimail.db で purchases と突合可能)")

    conn.close()
    print("\n" + "=" * 64)


def build_into_betimail(work_db: str, betimail_db: str, add_preview: bool = False) -> None:
    """作業用 DB から betimail の portal_* テーブルへ会員・資産・報酬・出金を投入する。

    ⚠ 最重要要件: 残高は user_point_setting.balance をそのまま採用し、
       投入後に会員別の完全一致検証を行う。1件でも不一致なら exit 1。
    """
    os.environ["BETIMAIL_DB_PATH"] = os.path.abspath(betimail_db)
    import importlib
    import config as _config
    importlib.reload(_config)
    import db as _db
    importlib.reload(_db)
    _db.init_db()

    w = sqlite3.connect(work_db)
    w.row_factory = sqlite3.Row

    print("[A] users / 残高 / ウォレットを収集")
    users: dict[int, dict] = {}
    for r in w.execute("SELECT id, email, name, role, wallet_address FROM users"):
        email = (r["email"] or "").strip().lower()
        if email:
            users[r["id"]] = {"email": email, "name": r["name"], "role": r["role"],
                              "wallet": r["wallet_address"]}
    balances = {r["user_id"]: float(r["balance"] or 0)
                for r in w.execute("SELECT user_id, balance FROM user_point_setting")}
    # user_wallet の最新行を優先、無ければ users.wallet_address
    wallets: dict[int, str] = {}
    for r in w.execute("SELECT user_id, wallet_address FROM user_wallet ORDER BY id"):
        if r["wallet_address"]:
            wallets[r["user_id"]] = r["wallet_address"]

    print("[B] 資産（購入・ステーク・transfer）を集計")
    purchased: dict[tuple[int, str], int] = {}
    for r in w.execute("SELECT user_id, nft, SUM(quantity) q FROM buy_nft GROUP BY user_id, nft"):
        purchased[(r["user_id"], r["nft"])] = int(r["q"] or 0)
    staked: dict[tuple[int, str], int] = {}
    for r in w.execute(
        """SELECT s.user_id, s.nft, s.number_nft_remain AS remain
           FROM staking_histories s
           JOIN (SELECT user_id, nft, MAX(id) AS mid FROM staking_histories
                 GROUP BY user_id, nft) m
             ON m.user_id = s.user_id AND m.nft = s.nft AND m.mid = s.id"""
    ):
        staked[(r["user_id"], r["nft"])] = max(0, int(r["remain"] or 0))
    tin: dict[tuple[int, str], int] = {}
    tout: dict[tuple[int, str], int] = {}
    for r in w.execute(
        "SELECT nft, from_id, to_id, amount FROM nft_change_history WHERE type = 4002"
    ):
        amt = int(r["amount"] or 0)
        if r["to_id"] in users:
            tin[(r["to_id"], r["nft"])] = tin.get((r["to_id"], r["nft"]), 0) + amt
        if r["from_id"] in users:
            tout[(r["from_id"], r["nft"])] = tout.get((r["from_id"], r["nft"]), 0) + amt

    print("[C] 報酬明細（commission_histories）を収集")
    cum_reward: dict[int, float] = {}
    reward_rows: list[dict] = []
    for r in w.execute(
        """SELECT id, user_id, nft, amount_commission, nft_staking, reward_distribution_day
           FROM commission_histories"""
    ):
        uid = r["user_id"]
        if uid not in users:
            continue
        amt = float(r["amount_commission"] or 0)
        cum_reward[uid] = cum_reward.get(uid, 0.0) + amt
        reward_rows.append({
            "external_id": r["id"],
            "distribution_id": None,
            "email": users[uid]["email"],
            "nft_type": r["nft"],
            "amount": amt,
            "units": r["nft_staking"],
            "balance_after": None,
            "rewarded_at": r["reward_distribution_day"],
        })

    print("[D] 会員レコードを構築")
    # 投入対象 = 購入 or 残高≠0 or ステーク>0 or transfer受領 のある user（role=10 管理者は除外）
    member_uids = (
        {uid for (uid, _n) in purchased}
        | {uid for uid, b in balances.items() if abs(b) >= 0.005 and uid in users}
        | {uid for (uid, _n), v in staked.items() if v > 0}
        | {uid for (uid, _n) in tin}
    )
    member_uids = {uid for uid in member_uids if uid in users and users[uid]["role"] != 10}
    members = []
    for uid in member_uids:
        u = users[uid]
        members.append({
            "email": u["email"],
            "name": u["name"],
            "portal_user_id": uid,
            "wallet_address": wallets.get(uid) or u["wallet"],
            "balance": balances.get(uid, 0.0),  # ⚠ 正本をそのまま。丸めない
            "cumulative_reward": round(cum_reward.get(uid, 0.0), 2),
            "source": "dump",
        })

    asset_rows = []
    nft_keys = set(purchased) | set(staked) | set(tin) | set(tout)
    for (uid, nft) in nft_keys:
        if uid not in member_uids:
            continue
        asset_rows.append({
            "email": users[uid]["email"],
            "nft_type": nft,
            "purchased_units": purchased.get((uid, nft), 0),
            "staked_units": staked.get((uid, nft), 0),
            "transferred_in": tin.get((uid, nft), 0),
            "transferred_out": tout.get((uid, nft), 0),
        })

    print(f"[E] 投入: members={len(members)} assets={len(asset_rows)} rewards={len(reward_rows)}")
    _db.clear_portal_tables()
    _db.bulk_upsert_portal_members(members)
    _db.bulk_upsert_portal_assets(asset_rows)
    n = _db.bulk_insert_portal_rewards(reward_rows)
    print(f"    報酬明細 {n} 件投入")

    print("[F] 出金申請 (request_withdraw) を withdraw_requests へ upsert")
    new_wd = 0
    for r in w.execute("SELECT * FROM request_withdraw"):
        uid = r["user_id"]
        u = users.get(uid, {})
        is_new = _db.upsert_withdraw({
            "external_id": r["id"],
            "source": "nftportal",
            "email": u.get("email", ""),
            "name": u.get("name"),
            "user_id": uid,
            "amount_usdt": float(r["amount"] or 0),
            "destination": r["destination"],
            "type": r["type"],
            "status": r["status"],
            "requested_at": r["created_at"],
            "action_at": r["action_at"],
            "secret_code": r["secret_code"],
        })
        if is_new:
            new_wd += 1
    print(f"    新規 {new_wd} 件（既存分は更新）")

    if add_preview:
        print("[G] プレビュー会員 (goldbenchan@gmail.com, source='preview') を追加")
        _db.bulk_upsert_portal_members([{
            "email": "goldbenchan@gmail.com", "name": "プレビュー管理者",
            "portal_user_id": None, "wallet_address": None,
            "balance": 123.45, "cumulative_reward": 67.89, "source": "preview",
        }])
        _db.bulk_upsert_portal_assets([
            {"email": "goldbenchan@gmail.com", "nft_type": "HOIHOI",
             "purchased_units": 10, "staked_units": 6, "transferred_in": 0, "transferred_out": 0},
            {"email": "goldbenchan@gmail.com", "nft_type": "MEMBER",
             "purchased_units": 20, "staked_units": 20, "transferred_in": 0, "transferred_out": 0},
        ])

    # ── 残高の完全一致検証（最重要）──
    print("\n[検証] 残高の完全一致チェック (dump user_point_setting vs portal_members)")
    mismatches = []
    for m in members:
        got = _db.get_portal_member(m["email"])
        if got is None:
            mismatches.append((m["email"], m["balance"], None))
            continue
        if abs((got["balance"] or 0) - m["balance"]) >= 0.005:
            mismatches.append((m["email"], m["balance"], got["balance"]))
    dump_pos_cnt = sum(1 for m in members if m["balance"] > 0)
    dump_pos_sum = sum(m["balance"] for m in members if m["balance"] > 0)
    totals = _db.portal_totals()
    print(f"    dump側:    残高>0 {dump_pos_cnt} 名 / 合計 ${dump_pos_sum:,.2f}")
    print(f"    betimail側: 会員 {totals['members']} 名 / 残高合計 ${totals['total_balance']:,.2f}")
    if mismatches:
        print(f"    ❌ 不一致 {len(mismatches)} 件:")
        for e, a, b in mismatches[:20]:
            print(f"       {e}: dump={a} betimail={b}")
        sys.exit(1)
    print(f"    ✅ 全 {len(members)} 会員の残高が旧ポータルと完全一致")

    print(f"\n✅ betimail DB ({betimail_db}) 投入完了")
    w.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dump", default="data/dashboard_20260715.sql")
    p.add_argument("--out", default="data/_import/portal_work.db")
    p.add_argument("--betimail-db", default="data/betimail.db",
                   help="email 突合（レポート）/ 投入先（--into-betimail）に使う betimail DB")
    p.add_argument("--report-only", action="store_true", help="既存の作業DBで集計のみ")
    p.add_argument("--into-betimail", action="store_true", help="作業DBから betimail へ投入")
    p.add_argument("--add-preview", action="store_true",
                   help="投入時にプレビュー会員 (goldbenchan) を追加（ソフトローンチ動作確認用）")
    args = p.parse_args()

    if not args.report_only and not args.into_betimail:
        if not os.path.exists(args.dump):
            print(f"❌ dump が無い: {args.dump}", file=sys.stderr)
            sys.exit(1)
        load_dump(args.dump, args.out)
        report(args.out, args.betimail_db)
    elif args.report_only:
        report(args.out, args.betimail_db)

    if args.into_betimail:
        if not os.path.exists(args.out):
            print(f"❌ 作業DBが無い: {args.out}（先に取込を実行）", file=sys.stderr)
            sys.exit(1)
        build_into_betimail(args.out, args.betimail_db, add_preview=args.add_preview)


if __name__ == "__main__":
    main()
