from __future__ import annotations

from typing import Any

from freddy_bot.chat.models import ChatMessage
from freddy_bot.utils import prompt_id, utc_now


def build_prompt_record(message: ChatMessage, source_url: str) -> dict[str, Any]:
    return {
        "id": prompt_id(message.text),
        "captured_at": utc_now(),
        "username": message.username,
        "text": message.text,
        "source_url": source_url,
        "status": "captured",
    }
