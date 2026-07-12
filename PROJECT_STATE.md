# Betimail プロジェクト状態ドキュメント

**最終更新**: 2026-06-22 (**v1.2.0 リリース** — ラッキーマスタード会員ポータル)
**目的**: 新規 Claude セッションでも即座に状況を把握し、開発・運用を継続できるようにする

> ⚠️ **v1.1.0 以降、本番運用モード**: `TEST_MODE=false` のため実会員にメールが届く状態です。テスト時は **送信先・件名・予約時刻** を必ず確認してから操作してください。
> セクション 15 の「v1.1.0 重要な変更まとめ」を最優先で読んでください。

---

## 0. このドキュメントの使い方

新しい Claude セッションを開始する時は、以下の順で確認すれば再開できます:

1. このファイル `PROJECT_STATE.md` を最初に読む
   - **特にセクション 15 (v1.1.0 重要な変更まとめ) を最優先**
2. `ai_knowledge.md` (AI エージェント用知識ベース) を読む
3. `README.md` (セットアップ手順) を確認
4. `git log --oneline v1.1.0..HEAD` で v1.1.0 以降の変更を確認

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
DEEPSEEK_API_KEY=<set>        # sk-... 
DEEPSEEK_MODEL=deepseek-chat
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

### 5.1.-1 Telegram 承認カード（仁氏が見る画面）

承認待ちが発生すると以下のカードが Telegram に届く:

```
📩 新着メール返信依頼 (ID: 123)
*送信者:* 山田太郎 <yamada@example.com>
*件名:* 配当金について
*確認理由:* 全件人手承認モード

━━━ 受信メール ━━━
（送信者のメッセージ）

━━━ AIの下書き ━━━
（AIが生成した返信案）

[✅ 承認して送信] [✏️ 直接編集]
[💬 AI と相談して修正]
[❌ 却下（返信しない）]
```

#### ボタンごとの動作

| ボタン | 動作 |
|---|---|
| ✅ **承認して送信** | 下書きをそのまま送信 |
| ✏️ **直接編集** | 次のメッセージで修正版本文を送る → そのまま送信 |
| 💬 **AI と相談して修正** | 自然言語で指示 (「もっと優しく」「短くまとめて」等) → AI が再生成 → 新しい下書きカードが返ってくる → 何度でも繰り返せる。仁氏が承認したら ✅ |
| ❌ **却下** | 送信しない |

#### AI 相談モード詳細

`💬 AI と相談して修正` をタップ後、自然言語で指示を送るたびに AI が知識ベース・購入履歴を踏まえて書き直す。例:
- 「もう少し優しく」
- 「謝罪を強調」
- 「短くまとめて」
- 「個別対応を強調」
- 「お問合せに具体的に答えて (ただし数字は出さずに)」

終了するには `/cancel` を送信。

### 5.1.0.5 TEST_MODE セーフモード（2026-05-15 から有効）

**現在は本番運用前の動作確認フェーズのため、`TEST_MODE=true`** です。

- `mail.send_email()` / `mail.send_reply()` は `TEST_ALLOWED_RECIPIENTS` (`.env` でカンマ区切り) に
  含まれるアドレス**以外**への送信を `TestModeBlockedError` で完全ブロック
- 現在の許可アドレス: `goldbenchan@gmail.com` (仁氏自身)
- Telegram の承認ボタンを押しても、宛先が許可外なら「🚫 TEST_MODE のため送信ブロック」と返す
- 一括送信 (`/api/send`) も同じく影響する

#### 本番運用への切り替え方

VPS で:
```bash
ssh betimail-vps "sed -i 's/^TEST_MODE=.*/TEST_MODE=false/' /opt/betimail/.env && \
  docker compose -f /opt/betimail/docker-compose.yml restart betimail"
```

#### 過去の事故

2026-05-15 に Telegram の `✏️ 直接編集` ボタンの動作確認中、
「どうやって編集する？」というテキストがそのまま `alichaaaan1003@gmail.com` (実在の会員) に送信された。
直後にお詫びメールを送信し、TEST_MODE を導入した。

### 5.1.0 送信ポリシー（2026-05-15時点）

**全件 Telegram 承認モード**で運用しています (`ALWAYS_HUMAN_APPROVAL=true`)。

- AI が confidence 高く判定しても **自動送信されず**、必ず Telegram に承認依頼
- 仁氏が Telegram から **✅承認 / ✏️編集 / ❌却下** を選ぶ
- 自動送信に切り替えたい場合: `.env` で `ALWAYS_HUMAN_APPROVAL=false`
  - その場合は信頼度 0.75 以上かつ AI が「安全」と判断したケースのみ自動送信

理由: コミュニティ内容がセンシティブで、AI 任せのリスクを避けるため。

### 5.1.1 DB未登録者からの問合せ

送信者のメールアドレスが DB にない場合（`get_member_by_email` が None）:
1. AI に `is_member=False` を渡す
2. AI は **メンバー前提の文言（「いつもご支援」等）を使わない**
3. **必ず `needs_human=True`**（自動送信させない）
4. reason に `[DB未登録]` プレフィックスを付与（Telegram通知でひと目で判別）
5. AI が生成する下書きは: お礼 → 登録未確認 → セルフチェックページ案内 (`/check`) → 別アドレス可能性 → 必要なら再返信を、という構成
6. 仁氏が Telegram で受け取り、状況確認後に承認 / 編集して送信

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
- **AI 反応が遅い/失敗**: DEEPSEEK_API_KEY 確認 + コンテナ再起動
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
4. このドキュメントも更新 (変更内容を Section 9 または最新リリース節に追記)

**特に予約配信の検証時の事故防止**:
- 配信日時を **30分以上先** に設定（焦らずキャンセルできる余裕）
- 件名に「【テスト】」を入れて識別
- 確認後は必ず `送信ジョブ` タブの X ボタンでキャンセル
- 緊急時は Section 16 の「緊急予約ジョブ全キャンセル」コマンドで一括停止

---

## 14. リリース履歴

| Tag | Date | 内容 |
|---|---|---|
| **v1.0.0** | 2026-05-15 | 初期リリース。4 種 NFT 保有者 1,066 名、買い取り出金監視、ユーザーセルフチェックページ含む |
| **v1.1.0** | 2026-05-16 | **本番運用開始**。OTP・予約配信・エイリアス統合・JST 表示統一・ラッキー報酬の二重実行防止 |
| **v1.2.0** | 2026-06-22 | **ラッキーマスタード会員ポータル**。元サイト恒久ダウンを受け betimail 内に会員ポータル＋管理＋日次分配を自前再構築（セクション 17 参照）|

---

## 15. v1.1.0 重要な変更まとめ（**新セッションは必ず読む**）

### 15.1 本番モード切替

| キー | v1.0.0 | v1.1.0 | 影響 |
|---|---|---|---|
| `TEST_MODE` | true | **false** | 実会員にメールが届く。一斉送信・OTP・AI返信全て本物 |
| `PUBLIC_CHECK_REQUIRE_OTP` | (未設定) | **true** | `/check` は OTP 必須 |
| `PUBLIC_CHECK_EXPOSE_NAME` | true | true | OTP 通過後に名前表示（C案維持）|
| `PUBLIC_CHECK_EXPOSE_NFT_TYPES` | false | **true** | OTP 通過後に NFT 種別も表示 |
| `PUBLIC_CHECK_OTP_TTL_SECONDS` | (新) | 600 | コード有効期限 10 分 |
| `PUBLIC_CHECK_OTP_RESEND_SECONDS` | (新) | 60 | 再送インターバル 60 秒 |

`/opt/betimail/.env.bak-*` にバックアップあり。緊急ロールバックは:
```bash
ssh betimail-vps "cp /opt/betimail/.env.bak-XXXXXX /opt/betimail/.env && docker compose restart betimail"
```

### 15.2 公開チェックページ `/check` の OTP 二段階認証

`POST /api/public/check`:
- **メンバー**: 6桁コードをメール送信 → `{verification_required:true, masked_email, expires_in}`
- **非メンバー**: 即 `{found:false}`（OTPメールは送らない＝スパム化防止）

`POST /api/public/check/verify`:
- 正しいコード入力で `{found:true, name, nft_types}` 返却
- 8回失敗で当該 OTP は破棄（lockout）
- レート制限: IP 10/分・120/時、email 5/5分

実装: `main.py` の `_issue_public_check_otp` / `_verify_public_check_otp`。コードは sha256+salt でハッシュ化保存（生コードは保存しない）。

### 15.3 `/check` ページのリデザイン

`frontend/src/app/check/page.tsx` 完全置換。

- 2カラム構成（暖色クリームのヒーロー + 白フォーム）
- `/check/community.jpg`（4人で肩組みイラスト）
- `support@betimail.uk` クリックでクリップボードコピー + Toast 通知
- iOS auto-zoom 防止 (input font-size: 16px)
- スマホ 920px 以下で縦並びレスポンシブ
- OTP UI（コード入力欄、再送ボタン、masked email 表示）

### 15.4 メルマガ予約配信機能 ⭐

#### 設計

| 観点 | 仕様 |
|---|---|
| **入力** | SendTab の `配信日時` フィールド（datetime-local、空 = 即時送信）|
| **保存** | DB は UTC、UI は JST 表示 |
| **最短/最長** | 1分以上先 / 30日以内 |
| **キャンセル** | `scheduled` 状態のみ可（`running` 以降は不可）|
| **重複防止** | SQLite atomic UPDATE で先勝ち（cron 並列でも安全）|
| **対象スナップショット** | 予約時に `bulk_job_targets` テーブルに宛先保存。実行時はそれを使うので、メンバー増減の影響を受けない |
| **失敗時の status** | `error` (旧: `done` で誤った成功通知が出ていたバグを修正)|

#### 関連ファイル

| ファイル | 変更内容 |
|---|---|
| `db.py` | `bulk_send_jobs` に `scheduled_at`, `segment`, `confirm_all` 追加 / `bulk_job_targets` 新規テーブル / `create_bulk_job(recipients=...)`, `cancel_scheduled_job`, `claim_due_scheduled_jobs`, `fail_bulk_job`, `get_bulk_job_targets` 関数 |
| `main.py` | `POST /api/send` に `scheduled_at` 受付 + `recipients` をスナップショット保存 / `POST /api/send/jobs/{id}/cancel` 追加 |
| `tools/run_scheduled_jobs.py` | **新規**: cron が1分毎に呼ぶ。`bulk_job_targets` から宛先取得 → 送信。Telegram 通知付 |
| `frontend/src/components/tabs/SendTab.tsx` | datetime-local ピッカー追加。送信ボタンが「予約配信を登録」に切替 |
| `frontend/src/components/tabs/JobsTab.tsx` | `予約済` バッジ + キャンセルボタン |

#### Cron 設定（VPS）

```cron
# 既存
0 20 * * *  /usr/bin/docker run --rm --env-file /opt/betimail/.env -v /opt/betimail/logs:/opt/betimail/logs betimail-scheduler:latest python /app/tools/daily_lucky_reward.py --notify-telegram >> /opt/betimail/logs/lucky_reward/cron.log 2>&1
*/30 * * * * /usr/bin/docker run --rm -e BETIMAIL_DB_PATH=/app/data/betimail.db --env-file /opt/betimail/.env -v /opt/betimail/logs:/opt/betimail/logs -v /opt/betimail/data:/app/data betimail-scheduler:latest python /app/tools/sync_nftportal_withdraws.py --notify-telegram >> /opt/betimail/logs/nftportal_sync/cron.log 2>&1
# v1.1.0 新規
* * * * *   /usr/bin/docker exec betimail python /app/tools/run_scheduled_jobs.py >> /opt/betimail/logs/scheduler/cron.log 2>&1
```

予約ジョブ用 cron は `docker exec` で常駐コンテナの中で実行（軽量、低レイテンシ）。

### 15.5 Gmail エイリアス重複統合

DB に 1066 メンバー登録だが、Gmail は `user+1@`, `user+2@`, `u.s.e.r@` を全て同一受信箱として扱うため **実ユニーク受信箱は 961**（最大は kaori さんで 22 通の重複登録）。

#### 動作

`/api/send` で送信時に `members.dedupe_by_inbox(recipients)` を呼ぶ:
- Gmail/Googlemail: `+tag` 削除 + ドット削除
- その他プロバイダ: `+tag` 削除のみ（ドットは意味があるので残す）
- 重複時は **NFT種別が最も多いレコードを採用**（テンプレ展開時の情報量重視）

UI 表示（SendTab フッター）:
```
1066 名 → 961 通（105 件のエイリアス重複を統合）に送信
```

#### 関連ファイル

- `members.py`: `canonical_inbox()`, `dedupe_by_inbox()` 関数追加
- `frontend/src/lib/ui.ts`: `canonicalInbox()`, `uniqueInboxCount()` ヘルパー
- `frontend/src/components/tabs/SendTab.tsx`: 重複統合数表示

DB レコード自体は無変更（購入履歴・ウォレットが個別にひもづくため保全）。

### 15.6 タイムゾーン統一（JST）

#### 背景

旧 `fmtDate` は ISO 文字列を単純スライスで表示していたため、UTC 保存値が JST に変換されず誤解を招いていた（"2026-05-16 00:28" と見えるが実は 09:28 JST）。

#### 修正

`frontend/src/lib/ui.ts`:
- `fmtDate` / `fmtDateShort`: ISO を `_parseIsoAsUtc()` で UTC 解釈 → `Intl.DateTimeFormat({timeZone:"Asia/Tokyo"})` で JST 表示
- `fmtDateTimeJst`: フル ja-JP ロケール + JST 固定
- 日時カラムヘッダーに `(JST)` 表記追加

予約日時の入力欄 (`datetime-local`) は **クライアントローカル時刻** のまま（ブラウザ仕様で変更不可、日本のPCなら JST）。

### 15.7 ダッシュボード/メンバー管理の表示バグ修正

#### 複数 NFT 保有者の表示

旧実装は `nft_type` カラム文字列全体を 1 キーとして lookup していたため、`"スペシャルマスタードNFT, ラッキーマスタードNFT"` のような複数保有者が:
- メンバー一覧でラベル崩れ
- ダッシュボード「メンバー内訳」で **スペシャル 0 名表示**（実際は 259 名）

修正:
- `MembersTab.tsx`: NFT 種別カラムを `split + 各種別ごとにバッジ表示`
- `DashboardTab.tsx`: `nftCounts` 集計を `split + filter + forEach` に変更

正しい数値:
| NFT種別 | 保有者数 |
|---|---:|
| 会員権NFT | 568 |
| パチスロホイホイ | 378 |
| ラッキーマスタード | 394 |
| スペシャルマスタード | 259 |

合計が 100% 超になるのは正しい（複数保有可能のため）。

#### 送受信履歴のメルマガ非表示デフォルト

961 通のメルマガ送信が `送受信履歴` を埋め尽くす問題に対応:

- `db.get_sent_emails(bulk='exclude'|'only'|'include')` 引数追加
- `/api/emails/sent?bulk=exclude` がデフォルト挙動 = 個別メール（AI返信・承認返信）のみ
- HistoryTab に切替プルダウン追加: `個別のみ / メルマガも含む / メルマガのみ`
- `bulk_job_id` を持つ行には `メルマガ #ID` バッジ表示
- 行クリックで本文展開（送信本文 + 受信本文 + AI下書き + Resend ID / Message-ID）

### 15.8 ラッキー報酬分配の堅牢化

`tools/daily_lucky_reward.py` 強化:

| 機能 | 効果 |
|---|---|
| **fcntl ファイルロック** (`.daily_lucky_reward.lock`) | cron ズレ + 手動実行による2重押下防止 |
| **state.json 1日1回ガード** | 同一 JST 日付では 2 回目以降スキップ。`--force` で上書き |
| **success 限定通知** | API レスポンスで `success=true` 確認時のみ ✅。それ以外は ⚠️ + exit 1 |
| **金額バリデーション** | `LUCKY_DAILY_MIN_AMOUNT` (default 1) / `LUCKY_DAILY_MAX_AMOUNT` (default 5000) |

### 15.9 OTP / Webhook / Telegram bot の堅牢化

Droid 監査で追加:

- **`webhook_email_id` カラム + UNIQUE インデックス**: `message_id` に加え 2 段防御で webhook 重複処理を防止
- **Telegram Bot 自動再起動ループ**: クラッシュ時 5秒バックオフで復帰
- **ログローテーション** (`tools/daily_lucky_reward.py`, `tools/sync_nftportal_withdraws.py`): 5MB × 5世代
- **`tools/backup_db.py`**: SQLite `.backup()` → `integrity_check` → gzip → 古い世代削除
- **ESLint flat config**: `npm run lint --max-warnings=0` で完全 pass
- **3層レート制限**: IP 10/分・120/時、email 5/5分

### 15.10 環境変数の v1.1.0 追加分

```ini
# OTP
PUBLIC_CHECK_REQUIRE_OTP=true
PUBLIC_CHECK_OTP_TTL_SECONDS=600
PUBLIC_CHECK_OTP_RESEND_SECONDS=60
PUBLIC_CHECK_EXPOSE_NAME=true
PUBLIC_CHECK_EXPOSE_NFT_TYPES=true

# 本番モード
TEST_MODE=false                     # ⚠️ 全送信解禁
TEST_ALLOWED_RECIPIENTS=goldbenchan@gmail.com  # 残す（誤って TEST_MODE=true に戻した時の安全策）

# ラッキー報酬の安全装置（任意、デフォルトあり）
LUCKY_DAILY_MIN_AMOUNT=1
LUCKY_DAILY_MAX_AMOUNT=5000
```

### 15.11 v1.1.0 で追加された API エンドポイント

| メソッド | パス | 用途 |
|---|---|---|
| POST | `/api/public/check/verify` | OTP コード検証、verified 後の name/NFT 返却 |
| POST | `/api/send/jobs/{id}/cancel` | 予約ジョブのキャンセル |

### 15.12 v1.1.0 で追加された DB テーブル/カラム

```sql
-- 新規テーブル
CREATE TABLE bulk_job_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    recipient_email TEXT NOT NULL,
    recipient_name TEXT,
    nft_type TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES bulk_send_jobs(id) ON DELETE CASCADE
);

-- bulk_send_jobs に追加カラム
ALTER TABLE bulk_send_jobs ADD COLUMN scheduled_at TEXT;
ALTER TABLE bulk_send_jobs ADD COLUMN segment TEXT;
ALTER TABLE bulk_send_jobs ADD COLUMN confirm_all INTEGER DEFAULT 0;

-- received_emails に追加カラム
ALTER TABLE received_emails ADD COLUMN webhook_email_id TEXT;

-- 新規 UNIQUE インデックス
CREATE UNIQUE INDEX idx_bulk_targets_job_email_unique ON bulk_job_targets(job_id, recipient_email);
CREATE UNIQUE INDEX idx_recv_webhook_email_id_unique ON received_emails(webhook_email_id) WHERE webhook_email_id IS NOT NULL AND webhook_email_id <> '';
```

`db.init_db()` の `_ensure_column()` で既存DBは自動マイグレートされる。

### 15.13 v1.1.0 でファイル追加

```
tools/run_scheduled_jobs.py       # 予約配信 cron worker (新規)
tools/backup_db.py                 # SQLite バックアップツール (新規)
frontend/eslint.config.mjs         # ESLint flat config (新規)
frontend/public/check/community.jpg  # /check ページ用イラスト (新規)
```

### 15.14 テスト統計

| 項目 | v1.0.0 | v1.1.0 |
|---|---|---|
| pytest 総数 | 33 | **54** |
| 追加されたテスト | - | OTP, alias dedup, scheduled job lifecycle, cancel, bulk filter |

### 15.15 v1.1.0 デプロイ時の操作履歴

1. 予約配信 cron 追加: `crontab -e` で `* * * * * docker exec betimail ...` 行追加
2. Scheduler イメージ再ビルド: `cp tools/daily_lucky_reward.py scheduler/tools/ && cd scheduler && docker build -t betimail-scheduler:latest .`
3. `.env` 更新: `TEST_MODE=false`, `PUBLIC_CHECK_REQUIRE_OTP=true`, `PUBLIC_CHECK_EXPOSE_NFT_TYPES=true`, OTP TTL/Resend 追加
4. 各種 backend 再ビルド: `docker compose build betimail && docker compose up -d betimail`

### 15.16 仁氏との重要な合意事項（v1.1.0 までに確認済）

- ✅ 「テスト用ダミーアドレスだけ認める」→ TEST_MODE で実装、その後本番運用開始 (`TEST_MODE=false`)
- ✅ 「betiは日本円を取り扱いしていない」→ 全 UI/AI で `$ USDT` 表記
- ✅ 「全件 Telegram 承認を必須にする」→ `ALWAYS_HUMAN_APPROVAL=true`（v1.1.0 でも維持）
- ✅ 「C案で実装（名前のみ表示）」→ デフォルト維持しつつ、OTP 通過後は NFT も解禁
- ✅ 「クライアントローカルTZで良い」→ JST 表記は明示するが TZ ロック しない
- ✅ 「送信時動的重複除外」→ DB 不変、送信時に Gmail 正規化

---

## 16. 次セッションの最初の確認コマンド集

```bash
# v1.1.0 の状態確認
git log --oneline v1.0.0..HEAD               # 今後 v1.1.0..HEAD に書き換え
ssh betimail-vps "docker compose -f /opt/betimail/docker-compose.yml ps"
ssh betimail-vps "crontab -l"
ssh betimail-vps "tail -20 /opt/betimail/logs/scheduler/cron.log"
ssh betimail-vps "tail -20 /opt/betimail/logs/lucky_reward/daily.log"
ssh betimail-vps "grep -E '^(TEST_MODE|PUBLIC_CHECK)' /opt/betimail/.env"

# 予約ジョブの確認
ssh betimail-vps "docker exec betimail python -c '
import sys; sys.path.insert(0, \"/app\")
import db
for j in db.list_bulk_jobs(limit=5):
    print(j[\"id\"], j[\"status\"], j[\"scheduled_at\"], j[\"subject\"][:30])
'"

# 緊急予約ジョブ全キャンセル（誤投入時）
ssh betimail-vps "docker exec betimail python -c '
import sys; sys.path.insert(0, \"/app\")
import db
with db.get_conn() as c:
    cur = c.execute(\"UPDATE bulk_send_jobs SET status=\\\"cancelled\\\" WHERE status=\\\"scheduled\\\"\")
    print(\"cancelled\", cur.rowcount, \"jobs\")
'"
```

---

## 17. v1.2.0 ラッキーマスタード会員ポータル（**新セッションは必ず読む**）

### 17.1 背景
元サイト `luckymustard.uk`（Laravel製の会員制報酬プラットフォーム、OVH `15.235.163.72`）が **2026-06-10 頃から恒久ダウン**し復旧不能に。毎晩20時JSTの報酬分配（ステーカーへの按分）が停止した。会員のために **betimail 内へ会員ポータル＋管理＋日次分配を自前で再構築**した。仁氏から入手した本番 SQL ダンプ（`luckymustard_bitcasino`、MySQL5.7、62MB）を正本としてデータ移行。

### 17.2 報酬ロジック（実データで検証済み・最重要）
- 報酬入金は元台帳 `balance_change_history.type = **5007**` で記録。
- **入金額 = 報酬対象NFT枚数 × (日次プール ÷ 総NFT枚数)**。
- **報酬対象枚数 = ステーク枚数**（`staking_histories`）であり `buy_nft` の購入枚数ではない（会員別に乖離あり）。現在の対象は **393名 / 685枚**（最終分配日2026-06-10にアクティブだった会員のその日の枚数の合計＝公式 total_nft_stake と一致）。
- 日次プールは時期で変動。立ち上げ期（2024-11〜2025-02）は $1,300〜1,850/日、段階的に低下し **2025-06頃から $352/日** で安定。累計分配は約 $360,197（575回, 2024-09-19〜2026-06-10）。

### 17.3 構成
- **DB（`db.py`）**: `lucky_members`（email/name/nft_count=報酬対象/owned_nft=購入/balance/cumulative_reward/source）・`lucky_distributions`・`lucky_rewards`。`create_lucky_distribution()` がDB内アトミック分配（`source='preview'` は分配・集計から除外）。
- **会員ポータル `/lucky`**（`frontend/src/app/lucky/`）: メールOTPログイン→残高ヒーロー・4指標タイル・残高推移SVGチャート・報酬履歴。**ダークテーマ固定（黒×ゴールド、明朝＋ゴシック）**。API/トークンは `frontend/src/lib/lucky.ts`（管理者トークンと分離）。
- **管理タブ「ラッキー報酬」**（`frontend/src/components/tabs/LuckyTab.tsx`）: 統計・手動分配（同日二重分配ガード=409＋force）・分配履歴。
- **認証**: 会員=メールOTP（`/api/lucky/login`・`verify`・`me`、`auth.issue_member_token` scope=lucky）。管理=既存 Bearer。
- **API**: `/api/lucky/login|verify|me`（会員）、`/api/lucky/distribute|distributions|admin/summary`（管理）。

### 17.4 日次分配 cron（死んだサイトを叩かない）
`tools/lucky_distribute.py`（DB内分配、`daily_lucky_reward.py` の代替）。`--backfill-from` で停止期間を補填、`--dry-run`/`--date`、Telegram通知、二重防止に `lucky_distribution_exists_for_date`。
```cron
0 20 * * * /usr/bin/docker exec -e LUCKY_LOG_DIR=/app/data/lucky_logs betimail \
  python /app/tools/lucky_distribute.py --notify-telegram >> /opt/betimail/logs/lucky_distribute/cron.log 2>&1
```
※旧 `daily_lucky_reward.py` の cron 行は削除済み。

### 17.5 データ移行（ETL）
`tools/import_lucky_dump.py`:
- `--dump <sql> --out <work.db>`: MySQLダンプを作業用SQLiteへ解析＋突合レポート。
- `--into-betimail --betimail-db <path>`: 作業DB→betimail本番DBへ投入（`clear_lucky_tables` で初期化してから）。
本番投入結果: 393名/685枚、報酬明細216,545件。SQLダンプはVPS `/opt/betimail/data/backup-luckymustard_-20260611010001.sql` に残置（PIIは私有VPSのみ、`data/*.sql` は gitignore）。

### 17.6 ソフトローンチ（限定公開）
`config.LUCKY_PORTAL_ALLOWED_EMAILS`（空=全員公開／非空=列挙アドレスのみログイン可）。現在 VPS `.env` に `LUCKY_PORTAL_ALLOWED_EMAILS=goldbenchan@gmail.com` を設定し**管理者限定公開**中。`goldbenchan@gmail.com` は `source='preview'` のダミー会員（実分配に影響なし）。
**全会員へ公開**: `.env` の `LUCKY_PORTAL_ALLOWED_EMAILS=` を空にして `docker compose up -d --build betimail`。

### 17.7 本番デプロイ手順（再掲）
1. `git push origin main` → Vercel が `/lucky`＋管理タブを自動デプロイ。
2. VPS: 本番DBバックアップ（`betimail.db.bak-prelucky` 取得済）→ `scp main.py db.py auth.py config.py tools/*.py` → `docker compose up -d --build betimail`（起動時マイグレーションで lucky_* 自動作成）。
3. SQLダンプを `/opt/betimail/data/` へ scp → ETL → `lucky_distribute.py --backfill-from <停止翌日>` → cron登録。
- ロールバック: `/opt/betimail/data/betimail.db.bak-prelucky` から復元。

### 17.8 残作業 / 今後
- ~~**全会員への公開**（限定公開ゲートの解除）~~ → **2026-06-22 公開済み**（`LUCKY_PORTAL_ALLOWED_EMAILS` は空 = 全会員ログイン可）
- 会員へ `https://admin.betimail.uk/lucky` の周知 → **2026-07-13 告知予定**
- 将来: 出金機能（当面不要のため未実装）、ラベル/デザイン微調整。

### 17.9 AI 返信エージェントのポータル問合せ対応（2026-07-13）

会員告知に伴うポータル関連問合せに AI が個別対応できるよう強化:

- **`ai_knowledge.md` セクション9 追加**: ポータルの基本情報（URL/OTPログイン/表示内容/データ移行・補填済みの事実）、よくある問合せと回答方針（ログイン不可・枚数相違=購入vsステーク・金額相違・出金希望・元サイトの行方・スペシャル対象外）、個別データの取り扱い原則
- **`ai.py`**: `_format_lucky_summary()` / `_build_lucky_block()` 追加。`generate_reply` / `regenerate_reply` に `lucky` 引数を追加し、送信者のポータル登録データ（報酬対象枚数・購入枚数・残高・累計報酬・直近日次報酬・最終入金日）をプロンプトに注入。ポータル未登録の beti 会員には「登録なし＝ログイン対象外、needs_human で取り次ぐ」の注記を注入
- **`main.py`** (webhook) / **`telegram_bot.py`** (AI相談モード): `db.get_lucky_dashboard(sender_email)` を取得して AI に受け渡し
- 回答方針: 金額はメール本文に書きすぎずポータルへ誘導 / 出金・将来の報酬は約束しない / 全件 Telegram 承認モードは維持（仁氏が最終確認）
- テスト: `tests/test_ai_fallback.py` に7件追加（計72件パス）

---

**運営: 仁氏 (`goldbenchan@gmail.com`)**
**開発支援: Claude Opus 4.7 (Anthropic) / v1.2.0 は Claude Opus 4.8**
