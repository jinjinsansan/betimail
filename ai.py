"""Claude による返信下書き生成。

- 知識ベース (ai_knowledge.md) をシステムプロンプトに含める
- Anthropic prompt caching を使い、コンテキスト料金を抑制
- tool_use で構造化出力を確実化
"""
import json
import os
import anthropic
from typing import Optional
from config import (
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AI_CONFIDENCE_THRESHOLD,
    AI_HISTORY_DEPTH, AI_KNOWLEDGE_PATH, ALWAYS_HUMAN_APPROVAL,
)
from logging_config import get_logger

log = get_logger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


def _load_knowledge() -> str:
    """ai_knowledge.md を読み込む。無ければ空文字列。"""
    if not os.path.exists(AI_KNOWLEDGE_PATH):
        log.warning("ai_knowledge.md not found at %s; AI will run without project context", AI_KNOWLEDGE_PATH)
        return ""
    try:
        with open(AI_KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        log.exception("Failed to load AI knowledge: %s", e)
        return ""


_KNOWLEDGE = _load_knowledge()


SYSTEM_PROMPT_BASE = """あなたは beti コミュニティのサポート担当 AI エージェントです。
あなたの役割は、運営代行の **仁** をサポートして、メンバー様 1 人 1 人の問い合わせメールに対して、
誠実かつ丁寧に下書き返信を作成することです。

メンバー様の多くは、長期間にわたり成果を待ち続けている投資家です。
不安・不満・落胆を抱えていらっしゃる方も少なくありません。
あなたは常に **お詫びと感謝を先に述べ、約束をせず、慎重な表現** で返信を作成してください。

## 最重要原則

1. **冒頭で受け止める**: お問い合わせのお礼、お待たせしていることへのお詫び
2. **誠実な姿勢**: 楽観論で誤魔化さない、進捗を装わない
3. **約束しない**: 具体的な金額、時期、確約となる表現は絶対に使わない
4. **慎重な言葉遣い**: 「現在進行中」「具体的に固まり次第」「ご報告できる段階になりましたら」など
5. **個別事情は運営へ取り次ぐ**: 自分で判断できない・してはいけない内容は人手承認に回す
6. **署名は必ず以下の形式**:

```
何卒よろしくお願いいたします。

beti 運営サポート
```

## 提出方法

submit_reply ツールを必ず使って返信を提出してください。

`confidence` は 0.0〜1.0 の自信度。`needs_human` は人手承認の要否。
迷ったら常に低めの confidence を設定してください。誤った自動送信は信頼を損ねます。

確認が必要な内容（金額、時期、個別判断、クレーム、強い感情など）は
必ず `needs_human: true` にして、`reason` に理由を記載してください。
"""


_REPLY_TOOL = {
    "name": "submit_reply",
    "description": "メール返信の下書きと、管理者確認の要否を提出します。",
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": "メール本文（日本語）。署名「beti 運営サポート」まで含めて完成形で返す。",
            },
            "confidence": {
                "type": "number",
                "description": "自信度 0.0〜1.0。自動送信して問題ないと判断する度合い。迷ったら低めに。",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "needs_human": {
                "type": "boolean",
                "description": "管理者（仁氏）の確認が必要かどうか。",
            },
            "reason": {
                "type": "string",
                "description": "needs_human が true の場合の理由を簡潔に。",
            },
        },
        "required": ["reply", "confidence", "needs_human"],
    },
}


def _build_history_messages(history: list[dict]) -> list[dict]:
    """過去のやり取りを user/assistant の会話形式に変換。"""
    messages = []
    for h in history:
        if h["direction"] == "received":
            messages.append({
                "role": "user",
                "content": f"[過去の受信メール]\n件名: {h.get('subject') or '(なし)'}\n本文:\n{h.get('body', '')}",
            })
        else:
            messages.append({
                "role": "assistant",
                "content": f"[過去の返信]\n件名: {h.get('subject') or '(なし)'}\n本文:\n{h.get('body', '')}",
            })
    return messages


def _build_system_blocks() -> list[dict]:
    """システムプロンプトを cache_control 対応のブロックリストで返す。

    知識ベース部分は長いので prompt cache を利かせる。"""
    blocks: list[dict] = [
        {"type": "text", "text": SYSTEM_PROMPT_BASE},
    ]
    if _KNOWLEDGE:
        blocks.append({
            "type": "text",
            "text": "\n\n## 知識ベース（beti コミュニティの背景・現状）\n\n" + _KNOWLEDGE,
            "cache_control": {"type": "ephemeral"},
        })
    return blocks


def _format_purchase_summary(purchases: dict) -> str:
    """db.get_purchase_summary() の結果を AI 向けテキストに整形。"""
    by_nft = purchases.get("by_nft") or []
    if not by_nft:
        return "（購入履歴の記録なし）"
    parts = []
    for row in by_nft:
        nft = row.get("nft_type", "?")
        units = row.get("total_units") or 0
        cnt = row.get("purchase_count") or 0
        first = row.get("first_purchase") or "?"
        returns = row.get("total_returns_usdt") or 0
        usdt = row.get("total_jpy") or 0  # 注: amount_jpy 列は実際にはUSDT額
        bits = [f"{cnt}回購入"]
        if units:
            bits.append(f"計{units}口")
        if usdt:
            bits.append(f"投資 ${usdt:,} USDT")
        if returns:
            bits.append(f"還元累計{returns:.2f} USDT")
        bits.append(f"初購入{first}")
        parts.append(f"- {nft}: " + " / ".join(bits))
    total_usdt = purchases.get("total_jpy") or 0
    total_returns = purchases.get("total_returns_usdt") or 0
    if total_usdt or total_returns:
        parts.append(f"\n累計: 投資 ${total_usdt:,} USDT / 還元 {total_returns:.2f} USDT")
    return "\n".join(parts)


def generate_reply(
    sender_name: str,
    sender_email: str,
    nft_type: str,
    original_subject: str,
    original_body: str,
    history: Optional[list[dict]] = None,
    purchases: Optional[dict] = None,
    is_member: bool = True,
) -> dict:
    """AI返信生成。{reply, confidence, needs_human, reason} を返す。"""
    if client is None:
        return {
            "reply": "",
            "confidence": 0.0,
            "needs_human": True,
            "reason": "ANTHROPIC_API_KEY が未設定です",
        }

    history_messages = _build_history_messages(history or [])

    purchase_block = ""
    if purchases:
        purchase_block = f"\n\n■ このメンバー様の購入履歴（DB記録）:\n{_format_purchase_summary(purchases)}\n"

    if is_member:
        guidance = """このメールに対し、知識ベースと最重要原則を踏まえて返信を作成し、
submit_reply ツールで提出してください。

★ 購入履歴が記載されている場合、メンバー様の事情・損失感を理解した上で
お返事してください。ただし、具体的な金額・時期・配当の数字は答えず、
個別の質問は仁氏（運営）に取り次ぐ姿勢を守ってください。"""
    else:
        guidance = """⚠️ 重要: 送信者のメールアドレスは beti コミュニティの登録メンバーリストに
**見つかりません**。これは以下のいずれかの可能性があります:
  (a) 別のメールアドレスで登録した方が、別アドレスで問い合わせている
  (b) 登録漏れ
  (c) コミュニティ外の方（スパム・誤送信・新規問合せ等）

このため、必ず以下のスタンスで返信下書きを作成してください:

1. **メンバー前提の文言は使わない**（「いつもご支援ありがとうございます」「ご購入の○○」など禁止）
2. **お問い合わせのお礼**から入る（中立的に）
3. **「現在の登録状況を確認できなかった」**ことを丁寧に伝える
4. **セルフチェックページの案内**:
   https://admin.betimail.uk/check
   で別アドレスでお試しいただくよう促す
5. **別アドレスで登録の可能性**にも触れる
6. 必要なら **改めてご返信を**と案内
7. 署名: beti 運営サポート

submit_reply の confidence は 0.5 以下、needs_human は **必ず true** にしてください。
仁氏が状況を確認した上で承認/編集する想定です。"""

    current_prompt = f"""今回返信すべきメールです。

送信者名: {sender_name or "不明"}
送信者メールアドレス: {sender_email}
保有 NFT 種別: {nft_type or "不明"}
登録状況: {'beti 登録メンバー' if is_member else '⚠️ 登録未確認（DBに該当なし）'}{purchase_block}

件名: {original_subject or "(件名なし)"}

本文:
{original_body}

{guidance}"""

    messages = history_messages + [{"role": "user", "content": current_prompt}]

    try:
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            system=_build_system_blocks(),
            tools=[_REPLY_TOOL],
            tool_choice={"type": "tool", "name": "submit_reply"},
            messages=messages,
        )
    except Exception as e:
        log.exception("AI generate_reply API error")
        return {
            "reply": "",
            "confidence": 0.0,
            "needs_human": True,
            "reason": f"AI API エラー: {e}",
        }

    # キャッシュ統計をログ出力
    try:
        usage = message.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0)
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0)
        log.info(
            "AI usage: input=%s output=%s cache_read=%s cache_creation=%s",
            usage.input_tokens, usage.output_tokens, cache_read, cache_creation,
        )
    except Exception:
        pass

    result: Optional[dict] = None
    for block in message.content:
        if getattr(block, "type", None) == "tool_use":
            result = dict(block.input)
            break

    if result is None:
        text = ""
        for block in message.content:
            if getattr(block, "type", None) == "text":
                text = block.text
                break
        result = _fallback_parse(text)

    conf = float(result.get("confidence", 0.0))
    if conf < AI_CONFIDENCE_THRESHOLD:
        result["needs_human"] = True
        if not result.get("reason"):
            result["reason"] = f"AI自信度が低い ({conf:.0%})"

    # 非メンバーは絶対に自動送信させない
    if not is_member:
        result["needs_human"] = True
        if not result.get("reason"):
            result["reason"] = "DB未登録の方からの問合せ（要本人確認）"
        else:
            result["reason"] = f"[DB未登録] {result['reason']}"

    # 全件人手承認モード (ALWAYS_HUMAN_APPROVAL=true) なら自動送信を無効化
    if ALWAYS_HUMAN_APPROVAL:
        result["needs_human"] = True
        if not result.get("reason"):
            result["reason"] = "全件人手承認モード（仁氏の最終確認後に送信）"

    result.setdefault("reply", "")
    result.setdefault("confidence", conf)
    result.setdefault("needs_human", True)
    result.setdefault("reason", "")
    log.info(
        "AI reply: conf=%.2f needs_human=%s reason=%r",
        result["confidence"], result["needs_human"], result.get("reason", ""),
    )
    return result


def _fallback_parse(text: str) -> dict:
    """JSON ブロック抽出のフォールバック。"""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        return {
            "reply": text or "",
            "confidence": 0.0,
            "needs_human": True,
            "reason": "AI 出力をパースできませんでした",
        }
