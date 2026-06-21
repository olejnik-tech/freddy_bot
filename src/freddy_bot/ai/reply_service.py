from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import Page

from freddy_bot.ai.codex_client import run_codex_reply
from freddy_bot.ai.prompt_builder import load_personality
from freddy_bot.ai.reply_quality import fallback_reply_body, is_invalid_reply_for_prompt
from freddy_bot.app.context_collection import collect_new_context
from freddy_bot.chat.parsing import normalize_message
from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger


async def ask_manual_reply(prompt: dict[str, Any], logger: Logger) -> str | None:
    logger.write("")
    logger.write(f"Prompt [{prompt['id']}]: {prompt['text']}")
    reply = await asyncio.to_thread(input, "Reply to send, or blank to skip: ")
    reply = reply.strip()
    return reply or None

async def ask_ai_reply(
    config: WatcherConfig,
    prompt: dict[str, Any],
    logger: Logger,
    auto_send_ai: bool,
    page: Page,
    seen: set[str],
    sent_replies: list[str],
) -> str | None:
    logger.write("Generating Codex reply...", "yellow")
    personality = load_personality(config.personality_file)
    logger.write(
        f"Using persona file: {config.personality_file} ({len(personality)} chars)"
    )
    logger.write(f"Conversation partner: {prompt.get('username') or 'unknown'}", "cyan")
    logger.write(f"Saved Codex prompt debug file: {config.last_codex_prompt_file}")
    reply = await asyncio.to_thread(run_codex_reply, config, prompt)

    extra_context = await collect_new_context(
        page, config, seen, sent_replies, logger, active_prompt=prompt
    )
    if extra_context:
        logger.write("Regenerating Codex reply with newer chat activity.")
        prompt = {
            **prompt,
            "new_context": extra_context,
        }
        reply = await asyncio.to_thread(run_codex_reply, config, prompt)

    reply = normalize_message(reply)
    if not reply:
        logger.write("Codex returned an empty reply.")
        return None

    if is_invalid_reply_for_prompt(reply, prompt):
        logger.write(f"Rejected weak or off-topic Codex reply: {reply}", "red")
        fallback = fallback_reply_body(prompt)
        if fallback:
            logger.write(f"Using scripted fallback reply: {fallback}", "yellow")
            return fallback

        if auto_send_ai:
            logger.write(
                "Auto-send is enabled, so rejected Codex reply was skipped.",
                "red",
            )
            return None

        replacement = await asyncio.to_thread(
            input, "Type replacement reply, or blank to skip: "
        )
        replacement = replacement.strip()
        return replacement or None

    logger.write(f"Codex suggested: {reply}", "yellow")
    if auto_send_ai:
        return reply

    user_reply = await asyncio.to_thread(
        input, "Press Enter to send, type replacement, or type /skip: "
    )
    user_reply = user_reply.strip()
    if user_reply == "/skip":
        return None
    return user_reply or reply
