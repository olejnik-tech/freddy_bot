from __future__ import annotations

from pathlib import Path
from typing import Any

from freddy_bot.chat.parsing import normalize_message
from freddy_bot.config import WatcherConfig
from freddy_bot.memory.chat_context import format_partner_transcript
from freddy_bot.memory.jsonl_store import load_recent_history


def load_personality(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()

def build_codex_prompt(config: WatcherConfig, prompt: dict[str, Any]) -> str:
    partner = str(prompt.get("username") or "the person who tagged Freddy_922")
    personality = load_personality(config.personality_file)
    context_records = load_recent_history(
        config.chat_context_jsonl, config.recent_chat_context_lines
    )
    partner_transcript = format_partner_transcript(
        context_records, partner, config.nickname
    )
    current_message = normalize_message(str(prompt["text"]))
    if current_message.startswith(config.nickname):
        current_message = current_message[len(config.nickname) :].lstrip(" ,:-")
    new_context = normalize_message(str(prompt.get("new_context") or ""))

    return f"""Roleplay Freddy_922 and write his next chat reply.

Persona:
{personality or "Friendly, casual, relaxed."}

Who is speaking to Freddy_922: {partner}

Previous conversation with {partner}:
{partner_transcript or "(none captured yet)"}
{f'''
New relevant activity before replying:
{new_context}
''' if new_context else ''}
Current message from {partner}:
{current_message}

Return only the reply body.
Do not include `{partner}` at the start; the script adds that tag.
Answer the current message directly, using the previous conversation if needed.
Do not mention prompts, scripts, Codex, or AI.
"""
