import anthropic
from config import ANTHROPIC_API_KEY, AI_CONFIDENCE_THRESHOLD

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """あなたはNFTコミュニティのサポート担当AIアシスタントです。
このコミュニティでは以下の4種類の利権付きNFTを販売しています：
- 会員権NFT
- パチスロホイホイNFT
- ラッキーマスタードNFT
- スペシャルマスタードNFT

メンバーからのメールに対して、丁寧で親切な日本語で返信を作成してください。
以下のような内容は自信を持って回答できます：
- NFTの一般的な説明
- コミュニティへの歓迎・感謝
- 利用方法の一般的な案内
- 問い合わせ内容の受付確認

以下のような内容は管理者への確認が必要です：
- 具体的な利権・配当・収益に関する数字
- 法律・税務に関する質問
- 返金・取引のキャンセル
- クレーム・トラブル対応
- 管理者のみが知る特定の情報

返信は必ず以下のJSON形式で返してください：
{
  "reply": "メール本文（日本語）",
  "confidence": 0.0〜1.0の数値（自信度）,
  "needs_human": true/false（管理者確認が必要かどうか）,
  "reason": "needs_humanがtrueの場合、その理由"
}"""


def generate_reply(
    sender_name: str,
    sender_email: str,
    nft_type: str,
    original_subject: str,
    original_body: str,
) -> dict:
    """
    AIが返信メールの下書きを生成する。
    戻り値: {"reply": str, "confidence": float, "needs_human": bool, "reason": str}
    """
    user_prompt = f"""以下のメールに返信してください。

送信者名: {sender_name or "不明"}
送信者メールアドレス: {sender_email}
保有NFT: {nft_type or "不明"}
件名: {original_subject or "(件名なし)"}

本文:
{original_body}

JSON形式で返信内容を返してください。"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    import json
    text = message.content[0].text.strip()
    # JSONブロックが```で囲まれている場合に対応
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    result = json.loads(text.strip())

    # needs_humanの最終判定（confidenceがしきい値未満の場合も確認が必要）
    if result.get("confidence", 1.0) < AI_CONFIDENCE_THRESHOLD:
        result["needs_human"] = True
        if not result.get("reason"):
            result["reason"] = f"AI自信度が低い ({result['confidence']:.0%})"

    return result
