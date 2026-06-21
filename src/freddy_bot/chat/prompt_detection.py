from __future__ import annotations

from freddy_bot.chat.models import ChatMessage
from freddy_bot.chat.parsing import (
    looks_like_own_timestamped_message,
    normalize_message,
    parse_own_directed_message,
)


def is_prompt_for_nickname(text: str, nickname: str) -> bool:
    normalized = normalize_message(text)
    return normalized.startswith(nickname) and not looks_like_own_timestamped_message(
        normalized, nickname
    )

def conversation_partner(message: ChatMessage, nickname: str) -> str | None:
    if is_prompt_for_nickname(message.text, nickname):
        return message.username

    own_message = parse_own_directed_message(message.text, nickname)
    if own_message:
        return own_message[0]

    return None

def is_recent_sent_reply_echo(text: str, nickname: str, sent_replies: list[str]) -> bool:
    normalized = normalize_message(text)
    if not normalized.startswith(nickname):
        return False

    return any(reply and reply in normalized for reply in sent_replies)
