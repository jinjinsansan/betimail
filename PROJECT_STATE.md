# Betimail プロジェクト状態ドキュメント

**最終更新**: 2026-05-15 (v1.0.0 リリース)
**目的**: 新規 Claude セッションでも即座に状況を把握し、開発・運用を継続できるようにする

---

## 0. このドキュメントの使い方

新しい Claude セッションを開始する時は、以下の順で確認すれば再開できます:

1. このファイル `PROJECT_STATE.md` を最初に読む
2. `ai_knowledge.md` (AI エージェント用知識ベース) を読む
3. `README.md` (セットアップ手順) を確認
4. `git log --oneline -20` で最近の変更を確認

主要ファイルへのリンク:
- `ai_knowledge.md` — beti コミュニティの詳細経緯
- `README.md` — セットアップ手順
- `db.py` — DB スキーマ
- `tools/` — スクレイピング・インポート・スケジューラ各種

---

## 1. プロジェクトの概要

### Betimail とは

**beti コミュニティ** 投資家向けのメルマガ配信 + AI 返信エージェント システム。

- **運営者**: 仁氏 (`goldbenchan@gmail.com`)
- **対象**: K氏 (マレーシア在住) が立ち上げた beti 投資家コミュニティのメンバー (1,066 名)
- **目的**:
  1. 仁氏からメンバーへの定期メルマガ配信
  2. メンバーからの個別問合せに対する AI エージェントによる自動返信（信頼度低なら人手承認）
  3. メンバー保有 NFT・買い取り資金の進捗をユーザー自身が確認できるセルフサービス

### 重要なドメイン

| URL | 用途 |
|---|---|
| `https://admin.betimail.uk/` | 管理画面 (仁氏のみ) - Vercel ホスト |
| `https://admin.betimail.uk/check` | **公開** メンバーセルフチェックページ |
| `https://api.betimail.uk/` | バックエンド API - VPS ホスト |
| `support@betimail.uk` | メンバーからの問合せ窓口 (AI 自動返信) |

---

## 2. beti コミュニティ背景（最重要）

beti は K氏 (マレーシア在住インフルエンサー) が 2024年に立ち上げた**個人投資家コミュニティ**。
4 種類の利権付き NFT を販売したが、2024年末からの日本国内オンラインカジノ規制で
**ほぼ全事業が頓挫**。現在は買い取り (バイバック) 対応中。

### 販売した 4 種類の NFT (全て現状ほぼ実現困難)

| No | NFT | 販売時期 | 当初の利権 | 現状 |
|---|---|---|---|---|
| 1 | **会員権NFT** | 2024-01〜03 | WA7 (オンカジ) の利権 | ベガンスター社が利益独占。**買い取り進行中**(微額) |
| 2 | **パチスロホイホイNFT** | 2024-04〜07 | デジタルパチスロのプロバイダー事業 | YOLO の RNG ライセンス取得停滞中。買い取り促進前段階 |
| 3 | **ラッキーマスタードNFT** | 2024 後半 | WA7 の月次2000万円分配 | WA7 アクセス不可。代替源での配当も微々たる |
| 4 | **スペシャルマスタードNFT** | 2024-2025 | クロフネカジノのスポーツブック | クロフネ自体が頓挫。買い取り促進準備中 |

### 重要な人物

- **K氏 / K**: マレーシア在住、beti 創設者・事業主体
- **仁氏 / 仁**: 国内運営、メルマガ送信者、本システムのユーザー
- **ベガンスター社**: WA7 (オンカジ) の実権を握り K氏と決裂した海外企業
- **YOLO グループ**: パチスロのライセンス取得サポート団体（停滞中）

詳細は `ai_knowledge.md` 参照。

---

## 3. システム全体像

### 3.1 インフラ

| レイヤー | 技術 |
|---|---|
| **VPS** | Xserver VPS / Ubuntu 26.04 / IP `162.43.90.178` / 2GB RAM |
| **ドメイン** | `betimail.uk` (Cloudflare 管理、`api` サブドメインのみ DNS-only) |
| **API** | FastAPI + Caddy リバプロ + 自動 TLS / Docker |
| **DB** | SQLite (WAL モード) at `/opt/betimail/data/betimail.db` |
| **Frontend** | Next.js 15.5.18 / Vercel (`admin.betimail.uk`) |
| **メール** | Resend (`support@betimail.uk` ドメイン検証済み) |
| **AI** | Claude Opus 4.7 (Anthropic API + prompt caching) |
| **通知** | Telegram Bot (`betimailbot`) |
| **Repo** | `github.com/jinjinsansan/betimail` |

### 3.2 SSH 接続

ローカルPC (Windows) から VPS:
```bash
ssh betimail-vps  # ~/.ssh/config に登録済み、エイリアス
```

設定:
```
Host betimail-vps
    HostName 162.43.90.178
    User root
    IdentityFile ~/.ssh/betimail_vps
    IdentitiesOnly yes
    ServerAliveInterval 60
```

VPS 上での作業ディレクトリ: `/opt/betimail/`

### 3.3 Docker コンテナ構成

VPS 上に以下のコンテナが常時稼働:

| コンテナ名 | 用途 |
|---|---|
| `betimail` | FastAPI バックエンド (port 127.0.0.1:8000) |
| `caddy` | リバプロ + TLS (port 80, 443) |
| `betimail-scheduler` (image) | cron から都度起動。スクレイピング・自動操作用 |

起動・停止:
```bash
cd /opt/betimail
docker compose up -d        # 起動
docker compose restart betimail  # 再起動
docker compose logs --tail=50 betimail  # ログ
```

### 3.4 環境変数 (`/opt/betimail/.env`)

`.gitignore` 対象。VPS にのみ存在。

```ini
# Admin (管理画面ログイン)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<set>          # 現状: 040505Aoi (チャット履歴に出てる、rotate 推奨)

# Resend
RESEND_API_KEY=<set>           # re_hCHvHUNL_... (rotate 推奨)
RESEND_FROM_EMAIL=support@betimail.uk
RESEND_FROM_NAME=beti 運営サポート
RESEND_WEBHOOK_SECRET=<set>    # whsec_... (rotate 推奨)

# Anthropic
ANTHROPIC_API_KEY=<set>        # sk-ant-... (rotate 推奨)
ANTHROPIC_MODEL=claude-opus-4-7
AI_CONFIDENCE_THRESHOLD=0.75   # 0.75 未満は人手承認
AI_HISTORY_DEPTH=5

# Telegram
TELEGRAM_BOT_TOKEN=<set>       # 8829858083:... (rotate 推奨)
TELEGRAM_CHAT_ID=197618639     # 仁氏

# CORS (Vercel 連携用)
CORS_ORIGINS=https://admin.betimail.uk,https://betimail.uk
CORS_ORIGIN_REGEX=https://.*.vercel.app

# Lucky Mustard 自動操作
LUCKY_ADMIN_EMAIL=admin@gmail.com
LUCKY_ADMIN_PASSWORD=<set>     # gyGwngF43N3W9jEC92QE (rotate 推奨)
LUCKY_DAILY_AMOUNT=352

# nftportal 監視
NFTPORTAL_ADMIN_EMAIL=admin@gmail.com
NFTPORTAL_ADMIN_PASSWORD=<set>  # ArT73HBzxdsfAX (rotate 推奨)

# その他
SEND_WELCOME_EMAIL=false
LOG_LEVEL=INFO
```

⚠️ チャット履歴に残った認証情報は適宜ローテーション推奨。

---

## 4. データベース構造

`/opt/betimail/data/betimail.db` (SQLite)

### 主要テーブル

| テーブル | 用途 | 件数 (2026-05-15時点) |
|---|---|---|
| `sent_emails` | 送信済みメール履歴 | (運用に応じ増加) |
| `received_emails` | 受信メール + AI 下書き | (運用に応じ増加) |
| `pending_approvals` | 承認待ち AI 返信 | (運用に応じ増加) |
| `bulk_send_jobs` | 一括送信ジョブ進捗 | (運用に応じ増加) |
| `templates` | メールテンプレート | (運用に応じ増加) |
| **`purchases`** | NFT 購入レコード | **2,160 件** |
| **`withdraw_requests`** | 買い取り出金履歴 | **10 件** (合計 $2,569 USDT) |

### `purchases` テーブル

各メンバーの NFT 購入1件 = 1行。

- `email` (lowercase, primary key for member identification)
- `nft_type` (`会員権NFT` / `パチスロホイホイNFT` / `ラッキーマスタードNFT` / `スペシャルマスタードNFT`)
- `amount_jpy` ← **列名は legacy。実際は USDT 額** (beti は日本円取扱なし)
- `units`, `transaction_id`, `purchased_at`, `team`, `returns_usdt` 等
- `source_file`: どのCSV/スクレイピング由来か (`PH管理...csv`, `kaiin.csv`, `luckymustard_3007`, `luckymustard_3008`, `afi_kaiin_diff` 等)

### `withdraw_requests` テーブル

nftportal.site の出金申請 = 買い取り資金の実支払い記録。

- `external_id` (nftportal 側の id)
- `email`, `name`, `amount_usdt`, `destination` (ウォレットアドレス)
- `status`: 0=申請中 / 1=処理中 / 2=完了 / 3=却下
- `requested_at`, `action_at`
- `notified_at`: Telegram通知済みフラグ（重複通知防止）

### members.csv (補助データ)

`/opt/betimail/data/members.csv` — `purchases` から自動再生成される。

形式: `name, email, nft_type, joined_date, notes`
- `nft_type`: カンマ区切りで複数 NFT を表現
- `notes`: 投資合計（USDT表記）/口数/還元累計

### NFT 種別ごと保有者数

| NFT | 保有者数 |
|---|---|
| 会員権NFT | **568** |
| パチスロホイホイNFT | **378** |
| ラッキーマスタードNFT | **394** |
| スペシャルマスタードNFT | **259** |
| **全ユニーク保有者** | **1,066** |

セグメント別:
- ラッキー単独保有 (スペシャル無し): **135 名**
- ラッキー + スペシャル両方: **259 名**

---

## 5. AI 返信エージェントの役割

### 5.1 動作フロー

```
メンバーが support@betimail.uk にメール送信
  ↓ Resend が受信 (MX レコード経由)
  ↓ webhook で /api/webhook/email (FastAPI) に POST
  ↓ 署名検証 (Resend webhook signature)
  ↓ APIで本文取得 (/emails/inbound/{email_id})
  ↓ DB から送信者の購入履歴 + 過去のやり取り を取得
  ↓ AI (Claude Opus 4.7) に送る:
     - システムプロンプト (お詫び・誠実・約束しない)
     - 知識ベース (ai_knowledge.md)
     - 購入履歴 (フォーマット済み)
     - 直近の会話履歴
     - 受信メール本文
  ↓ tool_use で構造化出力 (reply, confidence, needs_human, reason)
  ↓ confidence >= 0.75 かつ needs_human=false なら自動返信送信
  ↓ それ以外は pending_approvals に格納 + Telegram に承認依頼を通知
```

### 5.2 トーン原則 (重要)

メンバーは長期間待たされた不安な投資家。AI は:

✅ **必須**:
- 冒頭でお詫びと感謝
- 誠実に状況を共有 (約束はしない)
- 慎重な表現: 「現在進行中」「具体的に固まり次第」
- 署名: `beti 運営サポート`

❌ **絶対に答えてはいけない**:
- 具体的な買い取り金額・時期
- 配当・分配金の数字
- 法律・税務の質問
- 返金請求・クレーム対応
- 新事業の詳細
- ベガンスター社・WA7・YOLO 等の断定的発言

詳細は `ai_knowledge.md` の Section 7 参照。

### 5.3 知識ベース

`ai_knowledge.md` がシステムプロンプトに自動投入される (prompt caching 利用)。
ここを更新すれば AI の回答品質を改善できる。

---

## 6. 運用中の自動化

### 6.1 cron スケジュール (VPS)

```bash
$ crontab -l
# 20:00 JST 毎日: ラッキーマスタード 報酬分配自動実行
0 20 * * * /usr/bin/docker run --rm --env-file /opt/betimail/.env \
  -v /opt/betimail/logs:/opt/betimail/logs \
  betimail-scheduler:latest \
  python /app/tools/daily_lucky_reward.py --notify-telegram \
  >> /opt/betimail/logs/lucky_reward/cron.log 2>&1

# 30分毎: nftportal の新規買い取り出金申請を検出
*/30 * * * * /usr/bin/docker run --rm \
  -e BETIMAIL_DB_PATH=/app/data/betimail.db \
  --env-file /opt/betimail/.env \
  -v /opt/betimail/logs:/opt/betimail/logs \
  -v /opt/betimail/data:/app/data \
  betimail-scheduler:latest \
  python /app/tools/sync_nftportal_withdraws.py --notify-telegram \
  >> /opt/betimail/logs/nftportal_sync/cron.log 2>&1
```

### 6.2 ラッキー報酬分配 (daily_lucky_reward.py)

- **動作**: luckymustard.uk admin にログイン → `/admin/lucky-mustard` → 黄色「報酬分配」ボタンクリック → モーダルに金額入力 → 赤い確定ボタン → API レスポンス確認 → スクショ4枚保存 → Telegram 通知
- **金額**: 既定 352 USDT (`LUCKY_DAILY_AMOUNT` で変更可)
- **証拠保存**: `/opt/betimail/logs/lucky_reward/shots/{tag}_01..04.png`

金額を一時変更:
```bash
ssh betimail-vps "sed -i 's/^LUCKY_DAILY_AMOUNT=.*/LUCKY_DAILY_AMOUNT=400/' /opt/betimail/.env"
```

手動実行（dry-run可）:
```bash
ssh betimail-vps "docker run --rm --env-file /opt/betimail/.env \
  -v /opt/betimail/logs:/opt/betimail/logs \
  betimail-scheduler:latest \
  python /app/tools/daily_lucky_reward.py --amount 400 --notify-telegram"
```

### 6.3 nftportal 出金監視 (sync_nftportal_withdraws.py)

- **動作**: nftportal.site admin にログイン → 2025-11 から当月まで月毎に `/admin/withdraw-history/get-data` を取得 → DB の `withdraw_requests` に upsert → 新規分があれば Telegram 通知
- **間隔**: 30 分毎
- **重複防止**: `notified_at` で通知済みフラグ管理

---

## 7. 公開ページ /check (ユーザー向け)

`https://admin.betimail.uk/check` — 認証不要

メンバーが LINE 等で「自分はメルマガに登録されているか」を不安に思った時に
自分自身でメールアドレスを入力して確認できる公開ページ。

- 入力: メールアドレスのみ
- 出力: 名前 + 保有 NFT 種別 + 「正常配信されます」
- 該当なし: 「考えられる理由」+ support@betimail.uk への誘導
- レート制限: 20回/分/IP

API: `POST /api/public/check` (認証不要)

---

## 8. 主要なスクリプト (tools/)

### スクレイパー (Playwright ベース)

| ファイル | 用途 |
|---|---|
| `scrape_luckymustard.py` | luckymustard.uk からユーザー一覧 |
| `scrape_afi.py` | afi.irah.uk から NFT/device 購入履歴 |
| `scrape_nftportal.py` | nftportal.site からユーザー + 出金履歴 |

### インポート

| ファイル | 用途 |
|---|---|
| `import_purchases.py` | PH/会員権 CSV → purchases テーブル (初回) |
| `import_lucky_special.py` | luckymustard 取引履歴 → purchases (type=3007 ラッキー / 3008 スペシャル) |
| `import_afi_kaiin_diff.py` | afi で発見した会員権 NFT 漏れ 62名を追加取込 |
| `sync_nftportal_withdraws.py` | nftportal 出金履歴 → withdraw_requests (cron) |

### 探索・調査 (一時用)

| ファイル | 用途 |
|---|---|
| `explore_*.py`, `probe_*.py`, `inspect_*.py` | API構造調査用、再利用は基本不要 |

### 日次自動操作

| ファイル | 用途 |
|---|---|
| `daily_lucky_reward.py` | 報酬分配ボタン自動操作 (cron) |

---

## 9. 今日 (2026-05-15) やったこと

### A. ラッキーマスタード保有者の取得

1. luckymustard.uk admin にログイン (Playwright)
2. CSRF (Laravel XSRF-TOKEN) を Cookie から抽出して付与
3. `/admin/transactions-history` の `type=3007` (ラッキー) と `type=3008` (スペシャル) を分離
4. 結果: ラッキー 394 名 / スペシャル 259 名

### B. 通貨表記の修正

- すべての `¥` を `$` USDT に統一 (beti は USDT 取引のみ)
- 修正範囲: AI プロンプト、メンバー編集UI、import スクリプトの notes 生成

### C. afi.irah.uk との突合

- afi.irah.uk admin スクレイピング (`/admin/nft/get-nft-purchase-history`, `/admin/device/get-device-purchase-history`)
- 会員権NFT: afi に 546 名、DB に 506 名 → 差分検証
  - hardcode (0円会員): 3名 → 取込まない
  - 実購入だが DB 未登録: **62 名 を追加** → 506 → **568 名**
- パチスロホイホイ: afi `list_user` 展開で 376 ≈ DB 378 で一致確認 → そのまま保持

### D. ラッキー報酬分配 自動化

- 毎日 20:00 JST に 352 USDT 入力 + 確定ボタン自動操作
- Playwright 公式 Docker イメージで scheduler コンテナ作成
- cron 設定 + Telegram 通知

### E. nftportal.site 連携 (買い取り資金)

- 初回 backfill: 2025-11 ~ 2026-04 の出金申請 10件 (合計 $2,569 USDT / 9 受取人)
- DB に `withdraw_requests` テーブル追加
- 30分毎 cron で新規検出 + Telegram 通知

### F. 管理UI で買い取り出金を可視化 + モック除去

- 新タブ「💰 買い取り出金」追加 (Withdraws Tab)
- メンバー編集モーダルに「買い取り受取」セクション追加
- Dashboard に買い取り集計カード追加
- モック値 `0.78 * recv7` を実 `auto_sent` 件数に置換
- Login の固定値 (v2.4.1, All systems operational) を実 /health 値に
- Sidebar の固定 username/email を実 token 値に

### G. ユーザー向け公開チェックページ

- `https://admin.betimail.uk/check`
- 公開 API `POST /api/public/check` (認証不要、レート制限あり)
- LINE 等で配信不安なメンバーへの自助ツール

### H. v1.0.0 タグ

`git tag v1.0.0` を打って GitHub に push 済み。

---

## 10. 残作業 / 未完了項目

### 即対応可能
- **APIキー・パスワードのローテーション**: チャット履歴に残った以下のシークレット
  - Resend API key, webhook secret
  - Anthropic API key
  - Telegram bot token
  - luckymustard / nftportal の admin password
  - betimail ADMIN_PASSWORD (`040505Aoi`)

### 仕様未確定
- **購入価格の意味**: 「1 口 = 1,000 USDT」なのか「1 口 = ¥1,000 換算」なのか確認待ち
  - 仁氏 「また後日 (別 DB と突合予定)」
- **DB-only 25 名 (会員権NFT)**: afi に居ないが DB に居る実購入者
  - メールアドレス変更等の可能性、要調査

### あったら便利
- スペシャルマスタード単独取得サイトのスクレイピング (現在は luckymustard の取引履歴から取得)
- パチスロホイホイ買い取りが始まったらそのサイト連携
- ダッシュボードに買い取り進捗のグラフ
- メンバーへ買い取り受取通知メール自動送信 (新規 withdraw 検出時)
- 文字化け修正 (`notes` フィールドが API JSON 経由で surrogate codepoint 化することがある)

---

## 11. よく使うコマンド集

### VPS

```bash
# 接続
ssh betimail-vps

# コンテナ状態
ssh betimail-vps "docker compose -f /opt/betimail/docker-compose.yml ps"

# API ログ確認
ssh betimail-vps "docker compose -f /opt/betimail/docker-compose.yml logs --tail=50 betimail"

# cron ログ確認
ssh betimail-vps "tail -30 /opt/betimail/logs/lucky_reward/cron.log"
ssh betimail-vps "tail -30 /opt/betimail/logs/nftportal_sync/sync.log"

# コード更新後の再起動
scp main.py betimail-vps:/opt/betimail/
ssh betimail-vps "cd /opt/betimail && docker compose up -d --build betimail"

# scheduler image rebuild (tools/ 更新後)
ssh betimail-vps "docker build -f /opt/betimail/scheduler/Dockerfile -t betimail-scheduler:latest /opt/betimail/scheduler/"

# DB アドホッククエリ
ssh betimail-vps "docker compose -f /opt/betimail/docker-compose.yml exec -T betimail python -c \"
import db
conn = db.get_conn()
for r in conn.execute('SELECT ...').fetchall():
    print(dict(r))
\""
```

### Frontend (ローカル)

```bash
# 開発サーバ
cd frontend && npm run dev

# ビルド
cd frontend && npx next build

# Vercel デプロイは git push で自動
```

### テスト

```bash
PYTHONUTF8=1 python -m pytest --tb=short
```

### よくある問題のリカバリ

- **Vercel ビルド失敗**: 通常 main 押せば自動デプロイ。Vercel dashboard で確認
- **AI 反応が遅い/失敗**: ANTHROPIC_API_KEY 確認 + コンテナ再起動
- **メールが届かない**: Resend ダッシュボードで bounce 状態確認、ドメイン verified か確認
- **Telegram 通知が来ない**: TELEGRAM_BOT_TOKEN と CHAT_ID が .env に正しく入っているか確認
- **cron が動かない**: `systemctl status cron` で確認、ログを確認

---

## 12. ファイル/ディレクトリ構造

```
betimail/
├── PROJECT_STATE.md       # このファイル
├── README.md              # セットアップ手順
├── ai_knowledge.md        # AI 知識ベース
├── main.py                # FastAPI エントリポイント
├── config.py              # 環境変数読み込み
├── auth.py                # Bearer token 認証
├── db.py                  # SQLite ラッパー + スキーマ
├── members.py             # CSV メンバー管理
├── mail.py                # Resend 送信ラッパー
├── ai.py                  # Claude 返信生成
├── telegram_bot.py        # Telegram 承認ボット
├── webhook.py             # Resend 署名検証
├── ratelimit.py           # レート制限
├── logging_config.py      # ロガー
├── requirements.txt
├── Dockerfile             # betimail 本体イメージ
├── docker-compose.yml     # betimail + Caddy
├── Caddyfile              # リバプロ設定
├── scheduler/             # cron 用 Playwright イメージ
│   └── Dockerfile
├── tools/                 # スクレイピング・インポート・自動化
│   ├── import_purchases.py
│   ├── scrape_luckymustard.py
│   ├── scrape_afi.py
│   ├── scrape_nftportal.py
│   ├── import_lucky_special.py
│   ├── import_afi_kaiin_diff.py
│   ├── daily_lucky_reward.py     # cron 20:00
│   ├── sync_nftportal_withdraws.py  # cron 30分毎
│   └── explore_*.py (調査用)
├── frontend/              # Next.js (Vercel)
│   ├── package.json
│   ├── next.config.mjs
│   ├── tsconfig.json
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx           # 管理画面 (要ログイン)
│       │   └── check/page.tsx     # 公開チェックページ
│       ├── components/
│       │   ├── Dashboard.tsx      # 管理画面コンテナ
│       │   ├── Login.tsx
│       │   ├── Sidebar.tsx
│       │   ├── Topbar.tsx
│       │   ├── MemberEditModal.tsx
│       │   ├── common.tsx
│       │   └── tabs/
│       │       ├── DashboardTab.tsx
│       │       ├── SendTab.tsx
│       │       ├── ApprovalsTab.tsx
│       │       ├── MembersTab.tsx
│       │       ├── HistoryTab.tsx
│       │       ├── TemplatesTab.tsx
│       │       ├── WithdrawsTab.tsx       # 買い取り出金
│       │       └── JobsTab.tsx
│       ├── lib/
│       │   ├── api.ts             # fetch クライアント
│       │   ├── auth.ts            # token 保存
│       │   ├── types.ts
│       │   ├── ui.ts              # NFT_TYPES, ラベル, ヘルパー
│       │   └── icons.tsx          # Lucide-style SVG
│       └── styles/
│           └── globals.css
├── tests/                 # pytest
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_ai_fallback.py
│   ├── test_db.py
│   ├── test_mail.py
│   ├── test_members.py
│   └── test_webhook.py
└── exports/               # ローカルのみ (.gitignore)
    ├── 会員権NFT_保有者リスト.csv
    ├── パチスロホイホイNFT_保有者リスト.csv
    ├── ラッキーマスタードNFT_保有者リスト.csv
    ├── スペシャルマスタードNFT_保有者リスト.csv
    └── _afi_*.json, _lucky_*.json (生スクレイピング結果)
```

---

## 13. 次セッション開始時のチェックリスト

新しい Claude セッションで作業を再開する時の確認項目:

- [ ] このファイルを読んだ
- [ ] `git log --oneline -10` で最近の変更を確認
- [ ] `ssh betimail-vps "docker compose ps"` で VPS 稼働状況確認
- [ ] `ssh betimail-vps "crontab -l"` で cron が生きているか確認
- [ ] 必要に応じて `crontab` ログを確認:
  - `tail /opt/betimail/logs/lucky_reward/cron.log`
  - `tail /opt/betimail/logs/nftportal_sync/sync.log`
- [ ] Vercel dashboard で最終デプロイ状態確認
- [ ] 仁氏に最近の問題・新規要望を確認

何か変更を加えたら必ず:
1. ローカルでテスト (`pytest` + `next build`)
2. git commit + push (Vercel 自動デプロイ)
3. VPS にも反映 (scp + docker compose up -d --build)
4. このドキュメントも更新 (変更内容を Section 9 に追記)

---

## 14. リリース履歴

| Tag | Date | 内容 |
|---|---|---|
| **v1.0.0** | 2026-05-15 | 初期リリース。4 種 NFT 保有者 1,066 名、買い取り出金監視、ユーザーセルフチェックページ含む |

---

**運営: 仁氏 (`goldbenchan@gmail.com`)**
**開発支援: Claude Opus 4.7 (Anthropic)**
