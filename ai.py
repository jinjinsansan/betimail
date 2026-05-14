"""Claude による返信下書き生成。tool_use で構造化出力を確実化。"""
import json
import anthropic
from typing import Optional
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AI_CONFIDENCE_THRESHOLD, AI_HISTORY_DEPTH
from logging_config import get_logger

log = get_logger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

SYSTEM_PROMPT = """あなたはNFTコミュニティのサポート担当AIアシスタントです。
このコミュニティでは以下の4種類の利権付きNFTを販売しています：
- 会員権NFT
- パチスロホイホイNFT
- ラッキーマスタードNFT
- スペシャルマスタードNFT

メンバーからのメールに対して、丁寧で親切な日本語で返信を作成してください。

【自信を持って自動返信してよい内容】
- NFTの一般的な説明
- コミュニティへの歓迎・感謝
- 利用方法の一般的な案内
- 問い合わせ内容の受付確認

【管理者への確認が必要な内容】
- 具体的な利権・配当・収益に関する数字
- 法律・税務に関する質問
- 返金・取引のキャンセル
- クレーム・トラブル対応
- 管理者のみが知る特定の情報

submit_reply ツールを必ず使って返信を提出してください。"""


_REPLY_TOOL = {
    "name": "submit_reply",
    "description": "メール返信の下書きと、管理者確認の要否を提出します。",
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": "メール本文（日本語）。署名は不要。",
            },
            "confidence": {
                "type": "number",
                "description": "自信度 0.0〜1.0。返信内容が正確かつ自動送信して問題ないと判断する度合い。",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "needs_human": {
                "type": "boolean",
                "description": "管理者の確認が必要かどうか。",
            },
            "reason": {
                "type": "string",
                "description": "needs_human が true の場合の理由。",
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


def generate_reply(
    sender_name: str,
    sender_email: str,
    nft_type: str,
    original_subject: str,
    original_body: str,
    history: Optional[list[dict]] = None,
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

    current_prompt = f"""今回返信すべきメールです。

送信者名: {sender_name or "不明"}
送信者メールアドレス: {sender_email}
保有NFT: {nft_type or "不明"}
件名: {original_subject or "(件名なし)"}

本文:
{original_body}

submit_reply ツールで返信内容を提出してください。"""

    messages = history_messages + [{"role": "user", "content": current_prompt}]

    try:
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
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

    # tool_use ブロックを探す
    result: Optional[dict] = None
    for block in message.content:
        if getattr(block, "type", None) == "tool_use":
            result = dict(block.input)
            break

    if result is None:
        # フォールバック: テキスト出力を JSON として強引にパース
        text = ""
        for block in message.content:
            if getattr(block, "type", None) == "text":
                text = block.text
                break
        result = _fallback_parse(text)

    # confidence しきい値で needs_human を上書き
    conf = float(result.get("confidence", 0.0))
    if conf < AI_CONFIDENCE_THRESHOLD:
        result["needs_human"] = True
        if not result.get("reason"):
            result["reason"] = f"AI自信度が低い ({conf:.0%})"

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
        # ```json ... ``` 形式
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
