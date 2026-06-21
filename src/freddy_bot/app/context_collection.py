from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from freddy_bot.browser.dom import extract_chat_messages
from freddy_bot.chat.parsing import looks_like_own_timestamped_message, parse_own_directed_message
from freddy_bot.chat.prompt_detection import is_recent_sent_reply_echo
from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger
from freddy_bot.memory.chat_context import append_chat_context
from freddy_bot.memory.user_memory import has_user_memory


async def collect_new_context(
    page: Page,
    config: WatcherConfig,
    seen: set[str],
    sent_replies: list[str],
    logger: Logger,
    active_prompt: dict[str, Any] | None = None,
    limit: int = 5,
) -> str:
    relevant_lines: list[str] = []
    logged_lines: list[str] = []
    messages = await extract_chat_messages(page, config.message_selectors)
    active_username = active_prompt.get("username") if active_prompt else None
    for message in messages:
        text = message.text
        if text in seen:
            continue
        seen.add(text)

        own_directed = parse_own_directed_message(text, config.nickname)
        if (
            config.ignore_own_timestamped_messages
            and looks_like_own_timestamped_message(text, config.nickname)
            and not own_directed
        ):
            logger.write(f"Ignored own timestamped message: {text}", "dim")
            continue

        if is_recent_sent_reply_echo(text, config.nickname, sent_replies):
            logger.write(f"Ignored recent sent reply echo: {text}", "dim")
            continue

        if own_directed:
            target, body = own_directed
            if target != active_username and not has_user_memory(config, target):
                logger.write(
                    f"Ignored first outbound message to untracked {target}: {body}",
                    "dim",
                )
                continue

        saved = append_chat_context(config, message)
        username = message.username or "unknown"
        line = f"{username}: {text}"
        if saved:
            logged_lines.append(line)

        if saved and (
            text.startswith(config.nickname)
            or own_directed
            or (active_username and message.username == active_username)
        ):
            relevant_lines.append(line)

    if logged_lines:
        logger.write("New chat activity saved while Codex was thinking:", "blue")
        for line in logged_lines[-limit:]:
            logger.write(f"  {line}", "blue")

    if logged_lines and not relevant_lines:
        logger.write("No new activity was relevant to the active tagged prompt.", "dim")

    return "\n".join(relevant_lines[-limit:])
