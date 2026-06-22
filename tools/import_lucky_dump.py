"""luckymustard_bitcasino の MySQL ダンプから、ラッキーマスタード会員ポータルに
必要なテーブルだけを抽出して作業用 SQLite に取り込み、突合検証レポートを出す。

元サイト (luckymustard.uk) が 2026-06-10 以降に恒久ダウンしたため、入手した SQL
ダンプを正本として betimail 内に会員ポータルを再構築する。Phase 1 = データ基盤。

対象テーブル:
  users                          会員アカウント (id / name / email)
  staking_histories              NFT ステーキング (number_nft_remain = 有効枚数 = 報酬対象)
  buy_nft                        NFT 購入 (quantity)
  balance_change_history         全取引台帳 (receiver_balance_at_current_time = 取引後残高)
  reward_distribution_histories  日次報酬分配ログ
  nft_change_history             NFT 譲渡履歴

使い方:
  python tools/import_lucky_dump.py \
      --dump data/backup-luckymustard_-20260611010001.sql \
      --out  data/_import/lucky_work.db
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

# 取り込む対象テーブル
TARGET_TABLES = [
    "users",
    "staking_histories",
    "buy_nft",
    "balance_change_history",
    "reward_distribution_histories",
    "nft_change_history",
]

CREATE_RE = re.compile(r"^CREATE TABLE `([^`]+)` \($")
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
            if line.startswith(")"):  # テーブル定義終わり
                cur = None
                continue
            cm = COL_RE.match(line)
            if cm:
                name = cm.group(1)
                # KEY / PRIMARY / CONSTRAINT などは COL_RE に当たらない (backtick 位置が違う)
                cols[cur].append(name)
    return cols


def parse_values(body: str):
    """`INSERT ... VALUES ` の後ろの `(...),(...),...` を行タプル列に分解する。

    MySQL の文字列リテラル (シングルクォート、\\ エスケープ) を尊重したステートマシン。
    各行は Python の値 (int/float/str/None) のリストで返す。
    """
    rows: list[list] = []
    i, n = 0, len(body)
    while i < n:
        if body[i] != "(":
            i += 1
            continue
        # 1 タプルを読む
        i += 1
        fields: list = []
        cur = []
        in_str = False
        while i < n:
            c = body[i]
            if in_str:
                if c == "\\":  # エスケープ: 次の 1 文字をそのまま
                    if i + 1 < n:
                        nxt = body[i + 1]
                        cur.append({"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(nxt, nxt))
                        i += 2
                        continue
                    i += 1
                    continue
                if c == "'":
                    # '' (エスケープされたクォート) か文字列終端か
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
            # 文字列の外
            if c == "'":
                in_str = True
                cur = []  # 文字列フィールド開始
                fields.append(("str_pending", cur))
                i += 1
                continue
            if c in ",)":
                # フィールド確定
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
    # 数値
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

    print("[2] INSERT 行を解析して取り込み")
    counts: dict[str, int] = {t: 0 for t in TARGET_TABLES}
    with open(dump_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith(INSERT_PREFIX):
                continue
            end = line.index("`", len(INSERT_PREFIX))
            table = line[len(INSERT_PREFIX):end]
            if table not in TARGET_TABLES:
                continue
            marker = "` VALUES "
            vi = line.index(marker)
            body = line[vi + len(marker):].rstrip()
            if body.endswith(";"):
                body = body[:-1]
            rows = parse_values(body)
            ncol = len(cols[table])
            # 列数が一致する行だけ投入 (壊れたパースは捨てる)
            good = [r for r in rows if len(r) == ncol]
            if len(good) != len(rows):
                print(f"    ⚠ {table}: {len(rows)-len(good)}/{len(rows)} 行が列数不一致でスキップ")
            ph = ", ".join("?" * ncol)
            conn.executemany(f'INSERT INTO "{table}" VALUES ({ph})', good)
            counts[table] += len(good)
    conn.commit()
    for t in TARGET_TABLES:
        print(f"    {t}: {counts[t]} 行")
    conn.close()
    print(f"[3] 作業用 DB を書き出し: {out_db}")


def report(out_db: str, holders_csv: str | None) -> None:
    conn = sqlite3.connect(out_db)
    conn.row_factory = sqlite3.Row
    q = lambda s, *a: conn.execute(s, a).fetchall()  # noqa: E731
    one = lambda s, *a: conn.execute(s, a).fetchone()[0]  # noqa: E731

    print("\n" + "=" * 60)
    print("  突合検証レポート (LUCKY_MUSTARD)")
    print("=" * 60)

    print(f"\n会員(users) 総数: {one('SELECT COUNT(*) FROM users')}")

    # --- ステーキング (有効 LUCKY NFT 枚数 = 報酬対象) ---
    # 各 user の最新 staking 行の number_nft_remain を採用
    conn.execute("""
        CREATE TEMP VIEW lucky_stake AS
        SELECT s.user_id, s.number_nft_remain AS remain
        FROM staking_histories s
        JOIN (
            SELECT user_id, MAX(id) AS mid
            FROM staking_histories
            WHERE nft='LUCKY_MUSTARD'
            GROUP BY user_id
        ) m ON m.user_id = s.user_id AND m.mid = s.id
    """)
    stakers = one("SELECT COUNT(*) FROM lucky_stake WHERE remain > 0")
    total_staked = one("SELECT COALESCE(SUM(remain),0) FROM lucky_stake WHERE remain > 0")
    print(f"LUCKY ステーカー数 (remain>0): {stakers}")
    print(f"LUCKY 有効ステーク総数: {total_staked}")

    # --- buy_nft からの保有(購入)枚数 ---
    owned = one("SELECT COALESCE(SUM(quantity),0) FROM buy_nft WHERE nft='LUCKY_MUSTARD'")
    owners = one("SELECT COUNT(DISTINCT user_id) FROM buy_nft WHERE nft='LUCKY_MUSTARD'")
    print(f"LUCKY 購入(buy_nft)合計枚数: {owned} / 購入者 {owners} 名")

    # --- 報酬分配履歴 ---
    rd = q("""SELECT nft, COUNT(*) c, MIN(time) mn, MAX(time) mx, SUM(amount) s
              FROM reward_distribution_histories GROUP BY nft""")
    print("\n報酬分配履歴 (reward_distribution_histories):")
    for r in rd:
        print(f"  {r['nft']:15s} 回数={r['c']:4d}  期間 {r['mn']} 〜 {r['mx']}  累計={r['s']:.2f} USDT")
    last = one("SELECT MAX(time) FROM reward_distribution_histories WHERE nft='LUCKY_MUSTARD'")
    last_stake = one("""SELECT total_nft_stake FROM reward_distribution_histories
                        WHERE nft='LUCKY_MUSTARD' ORDER BY time DESC LIMIT 1""")
    print(f"  → 最後の LUCKY 分配: {last} / その時の total_nft_stake={last_stake}")
    print(f"  → staking 集計({total_staked}) と total_nft_stake({last_stake}) の差: {total_staked - (last_stake or 0)}")

    # --- 残高 (balance_change_history の最新 receiver 残高) ---
    # 各 user の最新取引後残高を採用 (to_id=user の最後の行)
    bal_total = one("""
        SELECT COALESCE(SUM(bal),0) FROM (
          SELECT b.receiver_balance_at_current_time AS bal
          FROM balance_change_history b
          JOIN (SELECT to_id, MAX(id) mid FROM balance_change_history GROUP BY to_id) m
            ON m.to_id=b.to_id AND m.mid=b.id
        )
    """)
    print(f"\n会員残高合計 (各人の最新取引後残高の和): {bal_total:.2f} USDT")

    # --- betimail 側保有者リストとの email 突合 ---
    if holders_csv and os.path.exists(holders_csv):
        import csv
        emails = set()
        with open(holders_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                e = (row.get("email") or row.get("Email") or "").strip().lower()
                if e:
                    emails.add(e)
        dump_emails = {(r[0] or "").strip().lower() for r in q("SELECT email FROM users")}
        inter = emails & dump_emails
        print(f"\nbetimail 保有者CSV({os.path.basename(holders_csv)}) email数: {len(emails)}")
        print(f"  dump users と一致: {len(inter)}")
        print(f"  CSV にあって dump に無い: {len(emails - dump_emails)}")
        print(f"  dump にあって CSV に無い: {len(dump_emails - emails)}")
    else:
        print("\n(保有者CSV未指定: --holders で betimail 側リストとの突合可能)")

    conn.close()
    print("\n" + "=" * 60)


def build_into_betimail(work_db: str, betimail_db: str) -> None:
    """作業用 DB から betimail の lucky_* テーブルへ会員・分配・報酬を投入する。

    報酬式: 入金額 = 保有NFT枚数 × (日次プール ÷ 総NFT枚数)。
    報酬入金は balance_change_history.type=5007（LUCKY のみ。SPECIAL 分配は履歴上ゼロ）。
    残高は各 user の最新取引後残高（from_id なら sender、to_id なら receiver）。
    """
    # betimail DB を差し替えてから db を import（config が env を読む）
    os.environ["BETIMAIL_DB_PATH"] = os.path.abspath(betimail_db)
    import importlib
    import config as _config
    importlib.reload(_config)
    import db as _db
    importlib.reload(_db)
    _db.init_db()

    w = sqlite3.connect(work_db)
    w.row_factory = sqlite3.Row

    print("[A] users / nft_count を集計")
    users = {r["id"]: (r["email"], r["name"]) for r in w.execute("SELECT id, email, name FROM users")}
    nft_count = {
        r["user_id"]: int(r["q"] or 0)
        for r in w.execute(
            "SELECT user_id, SUM(quantity) q FROM buy_nft WHERE nft='LUCKY_MUSTARD' GROUP BY user_id"
        )
    }

    # 報酬対象(ステーク)枚数 = 最後の分配日にアクティブだった会員の、その日の枚数。
    # 合計が最後の total_nft_stake(=685) に一致する＝「停止した所から再開」の正確な基準。
    last_dist_date = (w.execute(
        "SELECT MAX(created_at) FROM balance_change_history WHERE type=5007"
    ).fetchone()[0] or "")[:10]
    print(f"[B] balance_change_history を走査（最終分配日={last_dist_date}）")
    latest_bal: dict[int, tuple[int, float]] = {}   # uid -> (max_id, balance)
    cum_reward: dict[int, float] = {}
    last_reward_at: dict[int, str] = {}
    eligible_nft: dict[int, int] = {}               # 最終分配日にアクティブな会員の枚数
    reward_rows: list[dict] = []
    cur = w.execute(
        """SELECT id, from_id, to_id, amount, sender_balance_at_current_time AS sb,
                  receiver_balance_at_current_time AS rb, type, description, created_at
           FROM balance_change_history"""
    )
    for r in cur:
        rid = r["id"]
        # 残高: from 側と to 側の双方を候補に
        if r["from_id"] in users:
            u = r["from_id"]
            if u not in latest_bal or rid > latest_bal[u][0]:
                latest_bal[u] = (rid, r["sb"] if r["sb"] is not None else (latest_bal.get(u, (0, 0))[1]))
        if r["to_id"] in users:
            u = r["to_id"]
            if u not in latest_bal or rid > latest_bal[u][0]:
                latest_bal[u] = (rid, r["rb"] if r["rb"] is not None else (latest_bal.get(u, (0, 0))[1]))
        # 報酬入金 (type=5007, 受取=to_id)
        if r["type"] == 5007 and r["to_id"] in users:
            u = r["to_id"]
            amt = float(r["amount"] or 0)
            cum_reward[u] = cum_reward.get(u, 0.0) + amt
            ca = r["created_at"]
            if ca and (u not in last_reward_at or ca > last_reward_at[u]):
                last_reward_at[u] = ca
            try:
                nc = int(r["description"]) if r["description"] not in (None, "") else None
            except (ValueError, TypeError):
                nc = None
            if ca and ca[:10] == last_dist_date:
                eligible_nft[u] = nc or 0
            reward_rows.append({
                "external_id": rid,
                "distribution_id": None,
                "email": users[u][0],
                "nft_count": nc,
                "amount": amt,
                "balance_after": r["rb"],
                "rewarded_at": ca,
            })

    print("[C] 会員レコードを構築")
    # nft_count = 報酬対象(ステーク)枚数。owned_nft = 累計購入枚数(参考)
    member_uids = set(nft_count) | set(cum_reward) | set(latest_bal) | set(eligible_nft)
    members = []
    for u in member_uids:
        email, name = users.get(u, (None, None))
        if not email:
            continue
        members.append({
            "email": email,
            "name": name,
            "lucky_user_id": u,
            "nft_count": eligible_nft.get(u, 0),
            "owned_nft": nft_count.get(u, 0),
            "balance": round(latest_bal.get(u, (0, 0.0))[1] or 0, 2),
            "cumulative_reward": round(cum_reward.get(u, 0.0), 2),
            "last_reward_at": last_reward_at.get(u),
            "source": "dump",
        })

    print("[D] 分配イベントを構築")
    dists = []
    for r in w.execute(
        "SELECT id, nft, time, amount, total_nft_stake FROM reward_distribution_histories"
    ):
        total = int(r["total_nft_stake"] or 0)
        amt = float(r["amount"] or 0)
        dists.append({
            "external_id": r["id"],
            "nft": r["nft"],
            "distributed_for": r["time"],
            "pool_amount": amt,
            "total_nft": total,
            "rate": (amt / total) if total else None,
            "recipients": 0,
            "status": "done",
            "created_by": "migration",
        })

    print(f"[E] 投入: members={len(members)} distributions={len(dists)} rewards={len(reward_rows)}")
    _db.clear_lucky_tables()
    _db.bulk_upsert_lucky_members(members)
    _db.bulk_insert_lucky_distributions(dists)
    n = _db.bulk_insert_lucky_rewards(reward_rows)
    print(f"    reward 明細 {n} 件投入")

    tot = _db.lucky_totals()
    print(f"\n✅ betimail DB ({betimail_db}) 投入完了")
    print(f"   会員(NFT保有>0): {tot['members']}  総NFT: {tot['total_nft']}")
    print(f"   残高合計: {tot['total_balance']:.2f} USDT  累計報酬合計: {tot['total_reward']:.2f} USDT")
    w.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dump", default="data/backup-luckymustard_-20260611010001.sql")
    p.add_argument("--out", default="data/_import/lucky_work.db")
    p.add_argument("--holders", default="exports/ラッキーマスタードNFT_保有者リスト.csv")
    p.add_argument("--report-only", action="store_true", help="既存の作業DBで集計のみ")
    p.add_argument("--into-betimail", action="store_true", help="作業DBから betimail へ投入")
    p.add_argument("--betimail-db", default="data/_import/betimail_lucky_test.db",
                   help="投入先 betimail DB（本番は data/betimail.db）")
    args = p.parse_args()

    if not args.report_only and not args.into_betimail:
        if not os.path.exists(args.dump):
            print(f"❌ dump が無い: {args.dump}", file=sys.stderr)
            sys.exit(1)
        load_dump(args.dump, args.out)
        report(args.out, args.holders)
    elif args.report_only:
        report(args.out, args.holders)

    if args.into_betimail:
        if not os.path.exists(args.out):
            print(f"❌ 作業DBが無い: {args.out}（先に取込を実行）", file=sys.stderr)
            sys.exit(1)
        build_into_betimail(args.out, args.betimail_db)


if __name__ == "__main__":
    main()
