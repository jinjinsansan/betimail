# ポータルサイト（betiダッシュボード）再構築 実装計画書

**作成日**: 2026-07-17 / **仕様確定**: 2026-07-20（仁氏回答反映）
**ステータス**: 主要仕様確定・実装着手可（残る確認事項はセクション8.2）
**前例**: v1.2.0 ラッキーマスタード会員ポータル（`PROJECT_STATE.md` セクション17）

---

## 0. 全体アーキテクチャ（2026-07-20 確定）

自前再構築するサイトは **2本立て** で、役割を明確に分担する:

| サイト | 時期 | 役割 |
|---|---|---|
| **ポータルサイト** `/portal` | **今回** | **お金を動かすサイト**。①ホイホイ買い取りの意思表示受付（不可逆）②管理画面から買い取り原資を「会員権NFTへ分配」「パチスロホイホイへ分配」（口数均等割り・手動）③会員がウォレットアドレス+金額を記入して出金申請 ④仁氏が申請を処理 |
| **白のダッシュボード**（afi.irah.uk 再構築） | **次期案件** | **見るサイト + 独自残高の出金**。会員権NFT保有枚数・パチスロホイホイ保有枚数・ウォレット残高の表示。白ダッシュボード残高の出金申請フォームを設置し、管理画面から処理できるようにする |

**残高は2系統で互いに干渉しない**:
- ポータルの残高 = **管理画面からの分配のみ**で増える（ポータル独自の台帳）
- 白のダッシュボードの残高 = afi 由来の残高のまま。ポータルとは別物として扱う

---

## 1. 背景と目的

会員向けポータルサイト（betiダッシュボード / nftportal.site 系)がアクセス不可の状態が続いており、
運営はポータルを betimail 内に自前で再構築することを最終決定し、2026-07-17 に全会員へメルマガ告知済み（961通、開発期間3週間の見込みと案内）。

**目的**:
1. パチスロホイホイ購入者が**買い取りの意思表示**をセルフサービスでできる
2. 仁氏が買い取り原資を**管理画面から口数按分で分配**できる
3. 会員が分配された残高の**出金申請**（ウォレットアドレス+金額）を出し、仁氏が処理できる
4. 会員が自分の資産（NFT保有・残高・報酬/出金履歴）を確認できる

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
| `user_point_setting` | 3,266 | **現在残高** `balance`（残高>0 は 326 名、合計 **$35,146.86**） | ✅ 採用・**残高の正本**（$1も違わず引き継ぐ。8.1-9） |
| `buy_nft` | 1,030 | NFT購入履歴（下表参照） | ✅ 採用（保有口数の根拠） |
| `staking_histories` | 1,385 | ステーキング履歴（type 1=stake / 2=解除） | ✅ 採用（報酬対象口数の根拠） |
| `commission_histories` | 2,863 | **報酬明細**（1入金=1行、`nft_staking` 枚数付き） | ✅ 採用（報酬履歴表示用） |
| `reward_distribution_histories` | 21 | 分配イベント（`total_nft_stake`, `amount`） | ✅ 採用（検証・履歴用） |
| `balance_change_history` | 2,871 | 残高変動台帳（type **5007=報酬入金** 2,863 / 2=出金 4 / 2001 4件） | ✅ 採用（残高検算用） |
| `request_withdraw` | 29 | **出金申請**（status 0/1/2/3。既存 `withdraw_requests` と同源） | ✅ 採用（既存テーブルと突合・統合） |
| `nft_change_history` | 1,868 | NFT増減台帳（4002=transfer 483 / 4003=staking 1,111 / 4004=解除 274） | ✅ 採用（枚数検算用） |
| `request_transfer_nft` | 495 | NFT移転申請 | △ 参考（履歴表示は任意） |
| `user_wallet` / `user_ip` | 747/748 | ウォレット・IP | △ wallet のみ（出金先の初期値表示用）|
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

### 3.1 やること（今回 = ポータルサイト）

1. **ETL**: `tools/import_dashboard_dump.py`（`import_lucky_dump.py` 踏襲）
2. **会員ポータル** `/portal`（**白基調テーマ**）: OTPログイン → 資産表示 + 買い取り意思表示 + 出金申請
3. **買い取りボタン**（ホイホイ購入者のみ表示）:
   - 押下 → 「**二度と元に戻せません**」の注意を1回表示 → 確定 → 記録 + Telegram通知
   - **継続ボタンは設置するがグレーアウト（押せない）** — 意思表示として受け付けるのは買い取りのみ
   - 確定後も保有枚数の表示は**残す**（「買い取り申請済み」バッジを付与）
4. **管理画面から手動分配**: 「会員権NFTへ分配」「パチスロホイホイへ分配」の2機能のみ。
   総額を入力 → 対象NFTの**保有口数に均等割り**（按分）→ 各会員のポータル残高に加算。cron 自動化はしない
5. **出金申請**: 会員がウォレットアドレス + **金額（一部指定可）** を記入して申請 → Telegram通知 → 仁氏が管理タブで処理（状態管理）
5b. **ステークボタン**: 未ステーク口数（購入+transfer受領−ステーク済）がある会員が、確認モーダル経由で一括ステークできる。
   ステーク分が分配対象口数に加算される。解除機能は作らない。`portal_staking_events` に記録
6. **管理タブ** `PortalTab`: 会員資産照会・買い取り申請一覧・分配実行・出金申請処理・統計
7. **AI返信エージェント連携**: 送信者のポータル資産データをプロンプト注入（lucky と同じパターン）

### 3.2 やらないこと（非スコープ）

- アフィリエイト/MLMタイトル報酬（`user_point`）の再現 — 表示・計算とも対象外
- USDT の自動送金（出金申請の実支払いは従来どおり手動オペレーション）
- NFT のオンチェーン操作（transfer / staking 操作）— 表示のみ
- 日次の自動分配 cron — 分配は仁氏が管理画面から手動実行
- 旧サイトのパスワードハッシュ移行（OTPログインのため不要。PII最小化）
- **白のダッシュボード（afi 再構築）** — 次期案件として別途計画（セクション12に概要のみ）

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
    wallet_address TEXT,               -- user_wallet 由来の初期値。出金申請時に更新可
    balance REAL DEFAULT 0,            -- ポータル残高 = 分配累計 - 出金(paid)累計
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

-- 分配イベント（管理画面からの手動実行 1回=1行）
CREATE TABLE portal_distributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nft_type TEXT NOT NULL,            -- 'MEMBER' | 'HOIHOI'
    total_amount REAL NOT NULL,        -- 仁氏が入力した総額 (USDT)
    total_units INTEGER NOT NULL,      -- 実行時点の対象総口数（スナップショット）
    member_count INTEGER NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

-- 分配明細（1会員×1分配=1行。会員の報酬履歴表示用）
CREATE TABLE portal_distribution_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    distribution_id INTEGER NOT NULL,
    member_email TEXT NOT NULL,
    units INTEGER NOT NULL,            -- 実行時点の保有口数
    amount REAL NOT NULL,              -- total_amount / total_units * units
    FOREIGN KEY (distribution_id) REFERENCES portal_distributions(id)
);

-- 旧サイト報酬明細（commission_histories 由来、閲覧用）
CREATE TABLE portal_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id INTEGER,
    member_email TEXT NOT NULL,
    nft_type TEXT,
    amount REAL,
    nft_staking INTEGER,
    distributed_at TEXT
);

-- ホイホイ買い取り 意思表示（不可逆）
CREATE TABLE buyback_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_email TEXT NOT NULL,
    nft_type TEXT NOT NULL DEFAULT 'HOIHOI',
    units INTEGER,                     -- 確定時点の保有全口数を記録
    status TEXT DEFAULT 'pending',     -- pending / confirmed / processing / paid / rejected
    note TEXT,                         -- 管理メモ
    requested_at TEXT NOT NULL,
    action_at TEXT,
    notified_at TEXT,                  -- Telegram通知済みフラグ
    UNIQUE(member_email, nft_type)     -- 1会員1回のみ（不可逆・取り下げ不可）
);

-- ステーク操作（新ポータル上のステークボタン。解除は無し）
CREATE TABLE portal_staking_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_email TEXT NOT NULL,
    nft_type TEXT NOT NULL,
    units INTEGER NOT NULL,            -- ステークした口数（実行時の未ステーク全量）
    staked_at TEXT NOT NULL
);

-- ポータル出金申請（会員入力: ウォレットアドレス + 金額）
CREATE TABLE portal_withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_email TEXT NOT NULL,
    amount REAL NOT NULL,              -- 一部出金可。申請時に balance 以下を検証
    destination TEXT NOT NULL,         -- ウォレットアドレス
    status TEXT DEFAULT 'pending',     -- pending / processing / paid / rejected / cancelled
    note TEXT,
    requested_at TEXT NOT NULL,
    action_at TEXT,
    notified_at TEXT
);
```

- 残高整合: `portal_members.balance` は分配時に加算、出金 `paid` 確定時に減算（申請時は減算しない。pending 合計 + 申請額 > balance なら 409）
- 旧サイトの出金履歴は既存 `withdraw_requests`（dump の `request_withdraw` を `external_id` で upsert 統合）を**閲覧用**として表示。新規出金は `portal_withdrawals` に記録
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
4. **残高の完全一致検証（最重要）**: `portal_members.balance` の初期値 = `user_point_setting.balance` をそのまま採用。
   投入後に dump と betimail DB を会員別に突合し、**1件でも不一致（誤差 $0.01 以上）があれば ETL 失敗として扱い、全件一致レポートを出力**する。
   合計 $35,146.86 / 残高>0 326 名の再現も必須チェック

**PII 注意**: SQL ダンプ・ZIP は git 追跡外（`.gitignore` の `*.zip` / `backup-*.sql` / `data/*.sql` で担保済み）。
VPS へは `scp` で `/opt/betimail/data/` に置き、ローカルの解凍物は作業後削除。

---

## 6. API 設計（FastAPI `main.py`）

### 会員向け（認証: メールOTP、lucky と同じ `issue_member_token` を scope=`portal` で発行）

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/portal/login` | email 受付 → OTP送信（portal_members 登録者のみ。レート制限は既存3層流用） |
| POST | `/api/portal/verify` | OTP検証 → member token 返却 |
| GET | `/api/portal/me` | 資産一式（NFT別資産・ポータル残高・分配/報酬履歴・出金申請状況・買い取り申請状況） |
| POST | `/api/portal/stake` | 未ステーク口数の一括ステーク（nft_type指定）。portal_assets.staked_units 加算 + イベント記録 |
| POST | `/api/portal/buyback` | 買い取り意思表示の確定（不可逆）。既に申請済みなら 409。Telegram通知 |
| POST | `/api/portal/withdraw` | 出金申請（amount, destination）。amount+pending合計 ≦ balance を検証。Telegram通知 |
| DELETE | `/api/portal/withdraw/{id}` | 出金申請の取り下げ（pending のみ。買い取り意思表示は取り下げ不可） |

### 管理向け（既存 Bearer 認証）

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/portal/admin/summary` | 会員数・NFT別集計・残高合計・買い取り/出金申請状況サマリ |
| GET | `/api/portal/admin/members?q=` | 会員検索 + 資産照会 |
| POST | `/api/portal/admin/distribute` | **手動分配**（nft_type: MEMBER/HOIHOI, total_amount, note）→ 口数按分で balance 加算。確認パラメータ必須 + 同日同種別の二重実行ガード（force で上書き） |
| GET | `/api/portal/admin/distributions` | 分配履歴 |
| GET | `/api/portal/admin/buybacks?status=` | 買い取り申請一覧 |
| PATCH | `/api/portal/admin/buybacks/{id}` | 状態遷移（confirmed / processing / paid / rejected）+ メモ |
| GET | `/api/portal/admin/withdrawals?status=` | 出金申請一覧 |
| PATCH | `/api/portal/admin/withdrawals/{id}` | 状態遷移。**paid で balance 減算**（アトミック） |

### 通知

- 新規買い取り意思表示 / 新規出金申請 → **Telegram に即時通知**（既存 bot 流用、`notified_at` で重複防止）
- 申請の状態変更（paid 等）→ 会員へメール通知は**任意機能**（Phase 3 で判断）

### AI 連携

- `db.get_portal_dashboard(email)` を追加し、webhook / telegram_bot の AI 呼び出しに注入
  （`get_lucky_dashboard` と並列。`ai.py` に `_build_portal_block()` を追加）
- `ai_knowledge.md` セクション10（追加済み）が回答方針を規定。実装確定後に「買い取りは不可逆」「出金申請の流れ」等の公知情報を追記する

---

## 7. フロントエンド

### 7.1 会員ポータル `/portal`（frontend/src/app/portal/）

**テーマ: 白基調**（ラッキーの黒×ゴールドと明確に差別化。運営の指定）
- ベース: 白 `#ffffff` / ライトグレー `#f6f7f9`、文字はダークネイビー系、アクセントは信頼感のある紺＋薄金
- `/check` ページ（暖色クリーム）と世界観を揃えつつ、資産ダッシュボードらしい端正なカードUI
- 構成（lucky ポータルの構造を流用して開発短縮）:
  1. OTPログイン画面（メール → 6桁コード）
  2. ヒーロー: ポータル残高（USDT）+ 会員名
  3. NFT資産タイル: 種別ごとに「購入口数 / ステーク口数」（買い取り確定後も表示は残す + 申請済みバッジ）
  4. **買い取りパネル**（HOIHOI 資産がある会員のみ表示）:
     - 「買い取りを申請する」ボタン（赤系・要注意の見た目）
     - **「継続する」ボタンはグレーアウト固定（disabled、押せない）**
     - 買い取り押下 → 確認モーダル「**この操作は二度と元に戻せません**」→ 確定ボタン → 完了
     - 確定後は状態バッジ表示（申請済み / 処理中 / 完了）。ボタンは無効化
  5. **出金申請パネル**: ウォレットアドレス入力（前回値を初期表示）+ 金額入力（一部出金可、残高超過はエラー）→ 確認 → 申請。pending 中の申請は取り下げ可
  6. 分配（報酬）履歴テーブル / 出金履歴テーブル（旧サイト分 + 新申請分）
- API クライアント・トークン保存は `frontend/src/lib/portal.ts` として lucky.ts と分離

### 7.2 管理タブ（frontend/src/components/tabs/PortalTab.tsx）

- サマリカード（会員数 / NFT別口数 / ポータル残高合計 / 買い取り申請数 / 出金 pending 数）
- **分配パネル**: 「会員権NFTへ分配」「パチスロホイホイへ分配」の2ボタン。総額入力 → 対象人数・口数・1口あたり額のプレビュー表示 → 確認 → 実行。分配履歴テーブル
- 買い取り申請テーブル: フィルタ（状態別）、行クリックで詳細＋状態変更＋メモ
- 出金申請テーブル: 同上。paid にすると残高減算
- 会員検索: email/名前 → 資産・履歴・申請の個別照会

---

## 8. 仕様の確定状況

### 8.1 確定した仕様（2026-07-20 仁氏回答）

| # | 項目 | 確定内容 |
|---|---|---|
| 1 | 買い取り金額 | ポータルには金額を表示しない。**原資は管理画面から総額入力 → 保有口数に均等割り（按分）で残高へ分配**。分配は仁氏が手動実行。対象は「会員権NFTへ分配」「パチスロホイホイへ分配」の2機能のみ |
| 2 | 継続ボタン | **設置するがグレーアウトで押せない**（意思表示は買い取りのみ受付） |
| 3 | 買い取りの不可逆性 | 押下時に「二度と元に戻せません」の注意を1回表示 → 確定。**取り下げ・変更不可** |
| 4 | 確定後の表示 | 保有枚数の表示は**残す**（申請済みバッジ付与） |
| 5 | 出金申請 | 会員がウォレットアドレス + 金額を記入。**金額指定の一部出金も可**。仁氏が管理画面で処理 |
| 6 | 残高の分離 | ポータル残高と白のダッシュボード残高は**別物・干渉しない**。ポータル残高は管理画面からの分配のみで増える |
| 7 | 分配 cron | 不要（手動分配のみ） |
| 8 | サイト構成 | ポータルは `/portal` 1本。白のダッシュボードは**別サイトとして次期案件**で再構築 |
| 9 | **旧ポータル残高の引き継ぎ** | **引き継ぐ。全員の残高を旧ポータルと $1 も違わず完全一致させる（最重要要件）**。ETL 検証で会員別の完全一致を必須化 |
| 10 | 分配の口数基準 | **ステーク口数**（ユーザーがステークしていることが分配の条件。lucky と同じ） |
| 11 | 買い取り確定者の扱い | **買い取りを押した会員も分配対象に入る**（分配から除外しない） |
| 12 | スペシャルマスタード | **必ず資産表示する**（78名） |
| 13 | **ステークボタン** | **新ポータルに設置する**（2026-07-20 確定）。未ステーク口数を持つ会員が自分でステークでき、ステークした分が分配対象になる（旧ポータルで未ステークだった購入者 — HOIHOI 169名等 — の救済路）。解除ボタンは作らない |

### 8.2 残る確認事項（★開発途中でも随時確認・仁氏了承済み）

1. **HOIHOI 分配対象の範囲**: 「買い取りを押すと分配対象に入る」の確認 — 買い取りを押していない会員（ステーク済み）も分配対象に含まれるか、それとも買い取り確定者のみが対象か
2. **ステークボタンの対象NFT・単位**: MEMBER/HOIHOI のみで良いか（分配対象種別）。全未ステーク口数の一括ステークで良いか、口数指定が必要か（実装は一括を既定とする）
3. **`LEADER` 1名 / `DIGITAL_PACHISURO` 1名**: 表示・分配対象に含めるか
4. **ベトナム法人との連携**: 今回のダンプが最終か、継続提供があるか（差分同期の要否）
5. **会員リスト差分の個別確認**: `exports/ポータル突合_旧ポータルのみ.csv` / `exports/ポータル突合_メルマガ名簿のみ.csv` を仁氏が確認（公開前まででよい）

---

## 9. セキュリティ・運用

- **ソフトローンチゲート**: `PORTAL_ALLOWED_EMAILS`（lucky の `LUCKY_PORTAL_ALLOWED_EMAILS` と同方式）。
  公開前は `goldbenchan@gmail.com` のみ + `source='preview'` のダミー会員で動作確認
- OTP は既存実装（sha256+salt、TTL 10分、再送60秒、8回失敗で破棄）を関数レベルで共通化して流用
- レート制限: 既存3層（IP 10/分・120/時、email 5/5分）
- **分配・出金 paid はアトミック更新**（SQLite トランザクション内で balance 検証 + 更新。lucky の `create_lucky_distribution` と同パターン）
- 分配の誤操作対策: 確認パラメータ必須 + 同日同種別ガード + プレビュー表示（総額/人数/1口あたり）
- 本番投入前に `betimail.db` バックアップ（`betimail.db.bak-preportal`）
- ロールバック手順・cron 追加の有無を `PROJECT_STATE.md` に実装時に追記

---

## 10. スケジュール（約3週間・告知と整合）

| 週 | 作業 | 完了条件 |
|---|---|---|
| **Week 1** | ETL 開発＋検証レポート／`portal_*` テーブル＋マイグレーション／API 骨格（login/verify/me） | 突合レポートを仁氏が確認・数値承認。pytest 追加分パス |
| **Week 2** | `/portal` UI（白テーマ）＋OTPログイン＋資産表示／管理タブ PortalTab（分配パネル含む）／AI 連携注入 | プレビュー会員でローカル E2E 確認。ソフトローンチ（管理者限定）開始 |
| **Week 3** | 買い取り意思表示フロー＋出金申請フロー（会員UI＋管理＋Telegram通知）／8.2 の回答反映／テスト拡充／VPS デプロイ | 仁氏の実機確認 → ゲート解除 → 新URL告知メルマガ配信 |

バッファ: 8.2 の回答待ちが長引いた場合も、残高初期値以外は実装を止めない設計（legacy_balance 両対応）。

**次期案件（本計画完了後）**: 白のダッシュボード（afi.irah.uk 再構築）。セクション12参照。

---

## 11. リスク

| リスク | 対策 |
|---|---|
| dump と betimail 既存データの件数乖離（会員権 547 vs 568 等） | Week 1 の突合レポートで全件洗い出し、公開前に仁氏承認を必須化 |
| 分配の誤操作（桁間違い・二重実行） | プレビュー表示 + 確認 + 同日同種別ガード + Telegram 実行通知 |
| 買い取りボタンの誤操作（不可逆のため） | 注意モーダル1回 + 確定の2段階。管理側で rejected に落とす救済は残す（DB上は可能） |
| ステーク数 > 購入数の会員の扱い | transfer 台帳で追跡し、説明不能な行はレポートに列挙して個別判断 |
| 会員からの「金額はいくらか」問合せ殺到 | ポータルには金額を出さず意思表示のみ。AI 回答方針は ai_knowledge.md §10 で needs_human 徹底 |
| PII 漏えい（ダンプ・ZIP） | git 追跡外を確認済み。VPS のみ保管、ローカル解凍物は削除 |

---

## 12. 次期案件: 白のダッシュボード（afi.irah.uk 再構築）概要メモ

ポータル完成後に着手。詳細計画は別途作成する。

- **役割**: 会員権NFT保有枚数・パチスロホイホイ保有枚数・ウォレット残高の**表示** + **白ダッシュボード残高の出金申請**
- **残高**: afi 由来の残高をそのまま使う（ポータル残高とは別系統・干渉しない）
- **出金申請**: 白のダッシュボード上に申請フォームを設置し、betimail 管理画面から仁氏が処理できるようにする
- **データ源**: afi.irah.uk の DB ダンプ入手可否を仁氏経由で確認（不可ならスクレイピング。過去に `scrape_afi.py` の実績あり）
- 認証・UI・管理タブは本ポータルの実装を流用
