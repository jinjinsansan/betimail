# ポータルサイト（betiダッシュボード）再構築 実装計画書

**作成日**: 2026-07-17
**ステータス**: 計画（実装未着手）
**前例**: v1.2.0 ラッキーマスタード会員ポータル（`PROJECT_STATE.md` セクション17）

---

## 1. 背景と目的

会員向けポータルサイト（betiダッシュボード / nftportal.site 系）がアクセス不可の状態が続いており、
運営はポータルを betimail 内に自前で再構築することを最終決定し、2026-07 に会員へ告知する。

**目的**:
1. 会員が自分の資産（NFT保有・ステーク状況・残高・報酬/出金履歴）をセルフサービスで確認できる
2. **パチスロホイホイ購入者向けの「買い取りボタン」「継続ボタン」** を設置する（今回の告知の核心）
3. 管理側（仁氏）が買い取り申請・会員資産を betimail 管理画面から一元管理できる

**方式**: ラッキーマスタードポータル（v1.2.0）と同じ流れ。
ベトナム法人提供の SQL ダンプを正本として ETL → betimail SQLite に投入 → Next.js ポータル + FastAPI。

---

## 2. 元DB分析（`dashboard_20260715.sql`）

- 入手物: `ポータルサイト関連DB.zip` → `dashboard_20260715.sql`（3.0MB、phpMyAdmin 4.4 / MySQL、ダンプ日 2026-07-15）
- Laravel 製・ベトナム語コメント（luckymustard と同系統の開発元）
- **データは新しい**: users の最終作成が 2026-07-13 → DB 自体は直前まで生きていた

### 2.1 テーブル一覧と採否

| テーブル | 件数 | 内容 | 移行 |
|---|---:|---|---|
| `users` | 3,266 | 会員マスタ（email 3,252 ユニーク、role=10 の管理者2名、他は一般） | ✅ 採用（購入実績のある会員に絞る） |
| `user_point_setting` | 3,266 | **現在残高** `balance`（残高>0 は 326 名、合計 **$35,146.86**） | ✅ 採用（残高の正本） |
| `buy_nft` | 1,030 | NFT購入履歴（下表参照） | ✅ 採用（保有口数の根拠） |
| `staking_histories` | 1,385 | ステーキング履歴（type 1=stake / 2=解除） | ✅ 採用（報酬対象口数の根拠） |
| `commission_histories` | 2,863 | **報酬明細**（1入金=1行、`nft_staking` 枚数付き） | ✅ 採用（報酬履歴表示用） |
| `reward_distribution_histories` | 21 | 分配イベント（`total_nft_stake`, `amount`） | ✅ 採用（検証・履歴用） |
| `balance_change_history` | 2,871 | 残高変動台帳（type **5007=報酬入金** 2,863 / 2=出金 4 / 2001 4件） | ✅ 採用（残高検算用） |
| `request_withdraw` | 29 | **出金申請**（status 0/1/2/3。既存 `withdraw_requests` と同源） | ✅ 採用（既存テーブルと突合・統合） |
| `nft_change_history` | 1,868 | NFT増減台帳（4002=transfer 483 / 4003=staking 1,111 / 4004=解除 274） | ✅ 採用（枚数検算用） |
| `request_transfer_nft` | 495 | NFT移転申請 | △ 参考（履歴表示は任意） |
| `user_wallet` / `user_ip` | 747/748 | ウォレット・IP | △ wallet のみ（出金先表示用）|
| `purchase_nft_status` | 755 | 購入確認ステータス | △ 参考 |
| `send_nft_history(_detail)` | 10/70 | NFT一括送付記録 | ❌ 不要 |
| `user_point` | 0行相当 | MLMタイトル報酬集計 | ❌ **非スコープ**（アフィリエイト再現しない） |
| `sessions` / `password_resets` / `migrations` / `redis_config` / `user_active_email` / `nft_reception_status` / `packet_buy_nft` / `nft_reward_history` | 少数 | Laravel内部・旧機能 | ❌ 不要 |

### 2.2 NFT種別ごとの実数（buy_nft 集計）

| NFT enum | 購入者数 | 総口数 | 対応する betimail 名称 |
|---|---:|---:|---|
| `MEMBER` | 547 | 28,450 | 会員権NFT |
| `HOIHOI` | 387 | 22,990 | パチスロホイホイNFT |
| `SPECIAL_MUSTARD` | 78 | 467 | スペシャルマスタードNFT |
| `LEADER` | 1 | 200 | （要確認：リーダー枠？） |
| `DIGITAL_PACHISURO` | 1 | 150 | （要確認：テスト？） |
| `LUCKY_MUSTARD` | 0 | 0 | ラッキーは別DB（v1.2.0で移行済み・対象外） |

ステーク総数: MEMBER 29,197 / HOIHOI 23,766 / SPECIAL 339 / DIGITAL_PACHISURO 198 / LEADER 58
（購入口数よりステーク数が多い種別あり → transfer 受領分のステークが混在。ETL検証で解明する）

### 2.3 既存 betimail DB との突合ポイント（ETL 時に必須）

| 項目 | dump | betimail 現状 | 差異 |
|---|---:|---:|---|
| 会員権NFT 保有者 | 547 | 568 | -21（afi 補完分 62 名との関係を調査） |
| パチスロホイホイ 保有者 | 387 | 378 | +9 |
| スペシャル 保有者 | 78 | 259 | luckymustard 側 DB と二重管理だった可能性大 |
| 出金申請 | 29 件 | `withdraw_requests` 10 件 | dump にはテスト申請（2024-12 の thomn…宛）を含む。`external_id` で突合 |

**方針**: 新ポータルの表示はこの dump を正本とする。ただし betimail `purchases` とのメール突合レポートを必ず出し、
大きな差異（漏れ・重複）は仁氏に確認してから公開する（ラッキー移行時と同じ手順）。

---

## 3. スコープ

### 3.1 やること

1. **ETL**: `tools/import_dashboard_dump.py`（`import_lucky_dump.py` 踏襲）
2. **会員ポータル** `/portal`（**白基調テーマ**）: OTPログイン → 資産ダッシュボード
3. **買い取り・継続ボタン**（パチスロホイホイ購入者のみ表示）→ 申請フロー + Telegram通知
4. **管理タブ** `PortalTab`: 会員資産照会・買い取り申請管理・統計
5. **AI返信エージェント連携**: 送信者のポータル資産データをプロンプト注入（lucky と同じパターン）

### 3.2 やらないこと（非スコープ）

- アフィリエイト/MLMタイトル報酬（`user_point`）の再現 — 表示・計算とも対象外
- USDT の自動送金（買い取り成立後の支払いは従来どおり手動オペレーション）
- NFT のオンチェーン操作（transfer / staking 操作）— 表示のみ
- 日次報酬分配の新規実行 — このポータルは**閲覧+買い取り申請**が主目的（ラッキーと違い分配 cron は作らない。
  分配が今も必要な種別があるかは要確認 → セクション8）
- 旧サイトのパスワードハッシュ移行（OTPログインのため不要。PII最小化）

---

## 4. データモデル（betimail SQLite に追加）

`db.py` の lucky_* 群と同じ流儀で `portal_*` 群を追加:

```sql
-- 会員（dump users のうち購入実績がある会員のみ）
CREATE TABLE portal_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_user_id INTEGER,          -- dump users.id
    email TEXT NOT NULL UNIQUE,        -- lowercase
    name TEXT,
    wallet_address TEXT,
    balance REAL DEFAULT 0,            -- user_point_setting.balance
    source TEXT DEFAULT 'dashboard_20260715',  -- 'preview' はプレビュー用（分配・集計から除外）
    created_at TEXT, updated_at TEXT
);

-- NFT別資産（1会員×1NFT種別=1行）
CREATE TABLE portal_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_email TEXT NOT NULL,
    nft_type TEXT NOT NULL,            -- MEMBER / HOIHOI / SPECIAL_MUSTARD / ...
    purchased_units INTEGER DEFAULT 0, -- buy_nft 合計
    staked_units INTEGER DEFAULT 0,    -- staking_histories 純増
    transferred_in INTEGER DEFAULT 0,  -- nft_change_history 4002 受領
    transferred_out INTEGER DEFAULT 0,
    UNIQUE(member_email, nft_type)
);

-- 報酬明細（commission_histories 由来、閲覧用）
CREATE TABLE portal_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id INTEGER,
    member_email TEXT NOT NULL,
    nft_type TEXT,
    amount REAL,
    nft_staking INTEGER,
    distributed_at TEXT
);

-- 買い取り / 継続 申請（新規機能の中核）
CREATE TABLE buyback_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_email TEXT NOT NULL,
    nft_type TEXT NOT NULL DEFAULT 'HOIHOI',
    choice TEXT NOT NULL,              -- 'buyback' | 'continue'
    units INTEGER,                     -- 申請口数（全口 or 部分。仕様確認後に確定）
    status TEXT DEFAULT 'pending',     -- pending / confirmed / processing / paid / rejected / cancelled
    note TEXT,                         -- 会員コメント・管理メモ
    requested_at TEXT NOT NULL,
    action_at TEXT,
    notified_at TEXT                   -- Telegram通知済みフラグ
);
```

- 出金履歴は既存 `withdraw_requests` を継続利用（dump の `request_withdraw` を `external_id` で upsert 統合）
- `clear_portal_tables()` + `bulk_upsert_*` を lucky と同様に用意し、再投入可能にする

---

## 5. ETL（`tools/import_dashboard_dump.py`）

`import_lucky_dump.py` の実績パターンを踏襲:

1. `--dump dashboard_20260715.sql --out work_portal.db`
   MySQL ダンプを解析して作業用 SQLite へ。**検証レポート**を標準出力:
   - 会員数 / NFT別購入者数・口数（セクション2.2 の値と一致するか）
   - 残高>0 の会員数 326 / 残高合計 $35,146.86 の再現
   - 検算: `user_point_setting.balance` ≒ Σ(balance_change_history) を会員別に突合し、乖離リストを出す
   - ステーク数検算: staking_histories vs nft_change_history(4003-4004)
   - betimail `purchases` とのメール突合（どちらか片方にしか居ない会員のリスト）
2. `--into-betimail --betimail-db data/betimail.db`
   `clear_portal_tables()` → portal_members / portal_assets / portal_rewards 投入 → `request_withdraw` を `withdraw_requests` に upsert
3. 除外ルール: 購入実績ゼロの users（3,266 → 実質 1,000 名弱の見込み）、`mode=0` テスト、role=10 管理者、
   明らかなテストレコード（2024-12 の thomn… 宛出金など）は投入時に除外しレポートに記載

**PII 注意**: SQL ダンプ・ZIP は git 追跡外（`.gitignore` の `*.zip` / `backup-*.sql` / `data/*.sql` で担保済み）。
VPS へは `scp` で `/opt/betimail/data/` に置き、ローカルの解凍物は作業後削除。

---

## 6. API 設計（FastAPI `main.py`）

### 会員向け（認証: メールOTP、lucky と同じ `issue_member_token` を scope=`portal` で発行）

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/portal/login` | email 受付 → OTP送信（portal_members 登録者のみ。レート制限は既存3層流用） |
| POST | `/api/portal/verify` | OTP検証 → member token 返却 |
| GET | `/api/portal/me` | 資産ダッシュボード一式（NFT別資産・残高・報酬履歴・出金履歴・買い取り申請状況） |
| POST | `/api/portal/buyback` | 買い取り or 継続の申請（choice, units）。二重申請ガード（同一NFTで pending があれば 409） |
| DELETE | `/api/portal/buyback/{id}` | 申請の取り下げ（pending のみ） |

### 管理向け（既存 Bearer 認証）

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/portal/admin/summary` | 会員数・NFT別集計・残高合計・申請状況サマリ |
| GET | `/api/portal/admin/members?q=` | 会員検索 + 資産照会 |
| GET | `/api/portal/admin/buybacks?status=` | 買い取り/継続 申請一覧 |
| PATCH | `/api/portal/admin/buybacks/{id}` | 状態遷移（confirmed / processing / paid / rejected）+ メモ |

### 通知

- 新規買い取り申請 → **Telegram に即時通知**（既存 bot 流用、`notified_at` で重複防止）
- 申請の状態変更（paid 等）→ 会員へメール通知は**任意機能**（Phase 3 で判断）

### AI 連携

- `db.get_portal_dashboard(email)` を追加し、webhook / telegram_bot の AI 呼び出しに注入
  （`get_lucky_dashboard` と並列。`ai.py` に `_build_portal_block()` を追加）
- `ai_knowledge.md` セクション10（追加済み）が回答方針を規定

---

## 7. フロントエンド

### 7.1 会員ポータル `/portal`（frontend/src/app/portal/）

**テーマ: 白基調**（ラッキーの黒×ゴールドと明確に差別化。運営の指定）
- ベース: 白 `#ffffff` / ライトグレー `#f6f7f9`、文字はダークネイビー系、アクセントは信頼感のある紺＋薄金
- `/check` ページ（暖色クリーム）と世界観を揃えつつ、資産ダッシュボードらしい端正なカードUI
- 構成（lucky ポータルの構造を流用して開発短縮）:
  1. OTPログイン画面（メール → 6桁コード）
  2. ヒーロー: 残高（USDT）+ 会員名
  3. NFT資産タイル: 種別ごとに「購入口数 / ステーク口数」
  4. **買い取り/継続 パネル**（HOIHOI 資産がある会員のみ表示）:
     - 現在の申請状況バッジ（未申請 / 申請中 / 処理中 / 完了）
     - 「買い取りを申請する」「継続する」ボタン → 確認モーダル（2段階確認、注意文言）
  5. 報酬履歴テーブル / 出金履歴テーブル
- API クライアント・トークン保存は `frontend/src/lib/portal.ts` として lucky.ts と分離

### 7.2 管理タブ（frontend/src/components/tabs/PortalTab.tsx）

- サマリカード（会員数 / NFT別 / 残高合計 / 申請 pending 数）
- 買い取り申請テーブル: フィルタ（状態別）、行クリックで詳細＋状態変更＋メモ
- 会員検索: email/名前 → 資産・履歴・申請の個別照会

---

## 8. 買い取り・継続フロー（仕様案 — ★要仁氏確認）

```
会員が /portal で「買い取り」or「継続」選択
  → 確認モーダル（内容と注意事項を明示、取り消し可能である旨）
  → buyback_requests に pending で記録
  → Telegram に申請カード通知（会員名/email/口数/選択）
  → 仁氏が管理タブで confirmed → (買い取りの場合) 支払い実施後 paid に更新
  → 会員ポータル上の状態バッジが更新される
```

**★実装前に確認が必要な仕様**（回答が揃い次第、計画を確定）:

1. **買い取り金額の算定**: 口数×単価か、購入額基準か。金額をポータルに表示するか（表示しない=申請のみ、が安全）
2. **申請単位**: 全口一括のみか、部分口数の指定を認めるか
3. **「継続」の効果**: 継続を選んだ会員のデータ上の扱い（以後の分配対象? 単なる意思表示の記録?）
4. **申請期限**: 締切を設けるか、いつでも変更可能か（buyback⇄continue の変更可否）
5. **対象範囲**: HOIHOI のみで確定か。`LEADER` 1名 / `DIGITAL_PACHISURO` 1名の扱い
6. **スペシャルマスタード 78名（この dump 内）**: ポータルに資産表示するか（luckymustard 側 259 名との重複整理）
7. **日次・定期分配**: このポータル対象 NFT で今後も分配が発生するか（発生するなら lucky_distribute 相当の cron が必要）
8. **「ポータルサイト」と「betiダッシュボード」**: 同一サイト1本で良いか（本計画は 1 サイト `/portal` に統合する前提）
9. **ベトナム法人との連携**: 今回のダンプが最終か、継続的にダンプ提供があるか（差分同期の要否）

---

## 9. セキュリティ・運用

- **ソフトローンチゲート**: `PORTAL_ALLOWED_EMAILS`（lucky の `LUCKY_PORTAL_ALLOWED_EMAILS` と同方式）。
  公開前は `goldbenchan@gmail.com` のみ + `source='preview'` のダミー会員で動作確認
- OTP は既存実装（sha256+salt、TTL 10分、再送60秒、8回失敗で破棄）を関数レベルで共通化して流用
- レート制限: 既存3層（IP 10/分・120/時、email 5/5分）
- 本番投入前に `betimail.db` バックアップ（`betimail.db.bak-preportal`）
- ロールバック手順・cron 追加の有無を `PROJECT_STATE.md` セクション18として実装時に追記

---

## 10. スケジュール（約3週間・告知と整合）

| 週 | 作業 | 完了条件 |
|---|---|---|
| **Week 1** | ETL 開発＋検証レポート／`portal_*` テーブル＋マイグレーション／API 骨格（login/verify/me） | 突合レポートを仁氏が確認・数値承認。pytest 追加分パス |
| **Week 2** | `/portal` UI（白テーマ）＋OTPログイン＋資産表示／管理タブ PortalTab／AI 連携注入 | プレビュー会員でローカル E2E 確認。ソフトローンチ（管理者限定）開始 |
| **Week 3** | 買い取り・継続フロー（会員UI＋管理＋Telegram通知）／セクション8の確認事項の反映／テスト拡充／VPS デプロイ | 仁氏の実機確認 → ゲート解除 → 新URL告知メルマガ配信 |

バッファ: セクション8 の仕様回答待ちが長引いた場合、Week 3 の買い取りフローのみ後追いリリースし、
「資産閲覧ポータル」を先行公開する選択肢を残す（告知文面上も「開発完了まで今しばらく」とし日付は約束していない）。

---

## 11. リスク

| リスク | 対策 |
|---|---|
| dump と betimail 既存データの件数乖離（会員権 547 vs 568 等） | Week 1 の突合レポートで全件洗い出し、公開前に仁氏承認を必須化 |
| 買い取り仕様が未確定のまま3週間経過 | 閲覧ポータル先行公開のプランB（上記） |
| ステーク数 > 購入数の会員の扱い | transfer 台帳で追跡し、説明不能な行はレポートに列挙して個別判断 |
| 会員からの「金額はいくらか」問合せ殺到 | ポータルには金額を出さず申請のみ。AI 回答方針は ai_knowledge.md §10 で needs_human 徹底 |
| PII 漏えい（ダンプ・ZIP） | git 追跡外を確認済み。VPS のみ保管、ローカル解凍物は削除 |
