# Betimail

NFTコミュニティ向けのサポートメール管理システム。
一斉送信・受信メールへの AI 自動返信・Telegram または Web 管理画面での承認フローを統合。

## 機能

- 📤 **一斉送信** — メンバーへの一斉メール配信。NFT種別でフィルタ可能。`{name}` `{nft_type}` `{email}` のプレースホルダ対応。送信ジョブ単位で進捗・成否をトラッキング
- 📥 **受信＋AI自動返信** — Resend の inbound webhook を受け取り、Claude が返信下書きを生成
- ⏳ **承認フロー** — AI が自信を持てない返信は Telegram と Web 管理画面の両方から承認・編集・却下できる
- 👥 **メンバー管理** — CSV ベース。Web UI で追加・編集・削除・CSV インポート/エクスポート、メンバー別の送受信履歴表示
- 📝 **テンプレート** — 件名・本文を保存して再利用
- 🚚 **送信ジョブ** — 一括送信の進捗をリアルタイム追跡

## アーキテクチャ

| ファイル | 役割 |
|---|---|
| `main.py` | FastAPI エントリポイント・全APIルート |
| `config.py` | 環境変数読み込み |
| `logging_config.py` | ロガー設定 |
| `auth.py` | HTTP Basic 認証依存性 |
| `ratelimit.py` | インメモリレートリミッタ |
| `webhook.py` | Resend webhook (svix) 署名検証 |
| `db.py` | SQLite ラッパー + マイグレーション |
| `members.py` | CSV メンバー管理（スレッドセーフ） |
| `mail.py` | Resend 送信ラッパー（スレッディングヘッダ対応） |
| `ai.py` | Claude tool_use による構造化返信生成 |
| `telegram_bot.py` | Telegram Bot（別スレッドで polling） |
| `templates/index.html` | SPA 管理画面 |

## セットアップ

### 1. 依存インストール

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. `.env` を作成

`.env.example` をコピーして値を埋める：

```powershell
Copy-Item .env.example .env
```

**最低限の必須項目:**

- `RESEND_API_KEY` — Resend のAPIキー
- `RESEND_FROM_EMAIL` — 送信元（Resend で検証済みドメイン）
- `DEEPSEEK_API_KEY` — DeepSeek のAPIキー (OpenAI互換)
- `ADMIN_PASSWORD` — **本番運用では必須**。未設定だと管理画面が公開状態になる

**任意（推奨）:**

- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — 承認依頼を Telegram に通知
- `RESEND_WEBHOOK_SECRET` — Resend Webhook の改竄検証用

### 3. Telegram Bot 準備（任意）

1. BotFather で Bot 作成 → トークン取得
2. その Bot に DM を送り、`https://api.telegram.org/bot<TOKEN>/getUpdates` で `chat.id` を取得
3. `.env` に設定（カンマ区切りで複数管理者対応）

### 4. Resend Inbound Webhook 設定

Resend ダッシュボード → Inbound Routing → Webhook URL に
`https://<your-domain>/webhook/email` を設定。
表示される Svix シークレット (`whsec_...`) を `.env` の `RESEND_WEBHOOK_SECRET` に。

### 5. 起動

```powershell
python main.py
```

開発時は uvicorn の `--reload` が効きます。本番では:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000
```

`http://localhost:8000/` で管理画面、`/health` で稼働確認。

## Docker での起動

```powershell
docker build -t betimail .
docker run -p 8000:8000 --env-file .env -v ${PWD}/data:/app/data betimail
```

## テスト

```powershell
pytest -v
```

## 注意事項

- `data/members.csv` と `data/betimail.db` は永続化対象。Docker 利用時は volume をマウント
- SQLite は WAL モードで動作。並行アクセス可能だが、超高負荷向けではない
- 添付ファイル・HTML リッチエディタは未対応
- `LOG_LEVEL=DEBUG` で詳細ログ
