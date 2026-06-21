from __future__ import annotations

from typing import Any

from freddy_bot.chat.models import ChatMessage
from freddy_bot.chat.parsing import normalize_message, parse_own_directed_message
from freddy_bot.chat.prompt_detection import conversation_partner
from freddy_bot.config import WatcherConfig
from freddy_bot.memory.jsonl_store import append_jsonl
from freddy_bot.memory.user_memory import append_user_memory
from freddy_bot.utils import utc_now


def append_chat_context(config: WatcherConfig, message: ChatMessage) -> bool:
    partner = conversation_partner(message, config.nickname)
    if not partner:
        return False

    record = {
        "seen_at": utc_now(),
        "username": message.username,
        "partner": partner,
        "text": message.text,
    }
    append_jsonl(config.chat_context_jsonl, record)

    append_user_memory(config, partner, message.text)
    return True

def append_direct_context(
    config: WatcherConfig, partner: str, username: str, text: str
) -> None:
    record = {
        "seen_at": utc_now(),
        "username": username,
        "partner": partner,
        "text": text,
    }
    append_jsonl(config.chat_context_jsonl, record)
    append_user_memory(config, partner, text)

def format_chat_context(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records:
        username = record.get("username") or "unknown"
        partner = record.get("partner") or "unknown"
        text = record.get("text", "")
        if text:
            lines.append(f"with {partner} | {username}: {text}")
    return "\n".join(lines)

def format_partner_transcript(
    records: list[dict[str, Any]], partner: str, nickname: str
) -> str:
    lines: list[str] = []
    for record in records:
        if record.get("partner") != partner:
            continue

        username = record.get("username") or "unknown"
        text = normalize_message(str(record.get("text", "")))
        own_directed = parse_own_directed_message(text, nickname)
        if own_directed:
            _, body = own_directed
            lines.append(f"{nickname}: {body}")
        elif username == partner:
            body = text
            if body.startswith(nickname):
                body = body[len(nickname) :].lstrip(" ,:-")
            lines.append(f"{partner}: {body}")
        elif username == nickname:
            if text.lower().startswith(partner.lower()):
                text = text[len(partner) :].lstrip(" ,:-")
            lines.append(f"{nickname}: {text}")
    return "\n".join(lines[-20:])

def format_history(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records:
        status = record.get("status", "unknown")
        if status == "captured":
            lines.append(f"Incoming: {record.get('text', '')}")
        elif status == "reply_sent":
            lines.append(f"Freddy_922 reply: {record.get('reply', '')}")
        elif status == "reply_skipped":
            lines.append(f"Skipped: {record.get('prompt', '')}")
    return "\n".join(line for line in lines if line.strip())
