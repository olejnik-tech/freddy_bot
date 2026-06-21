from __future__ import annotations

import re
from typing import Any

from freddy_bot.chat.parsing import normalize_message


def is_bad_codex_reply(reply: str) -> bool:
    lowered = reply.lower()
    bad_phrases = (
        "send me the",
        "what's the message",
        "what’s the message",
        "whats the message",
        "what message",
        "what should",
        "what is freddy",
        "what freddy",
        "provide the",
        "provide more context",
        "need more context",
        "i need context",
        "what context",
        "chat context",
        "chat message/context",
        "incoming message",
    )
    generic_greetings = (
        "what's up",
        "what’s up",
        "whats up",
        "good to see you",
    )
    return any(phrase in lowered for phrase in bad_phrases) or any(
        phrase in lowered for phrase in generic_greetings
    )

def is_too_weak_reply(reply: str) -> bool:
    lowered = normalize_message(reply).lower().strip(" .,!?:;")
    words = re.findall(r"[A-Za-z]+", lowered)
    weak_exact = {"got it", "okay", "ok", "sure", "hey", "hello", "hi"}
    weak_phrases = ("what's up", "whats up", "good to see you")
    return lowered in weak_exact or len(words) < 4 or any(
        phrase in lowered for phrase in weak_phrases
    )

def is_invalid_reply_for_prompt(reply: str, prompt: dict[str, Any]) -> bool:
    return is_bad_codex_reply(reply) or is_too_weak_reply(reply)

def fallback_reply_body(prompt: dict[str, Any]) -> str | None:
    return None
