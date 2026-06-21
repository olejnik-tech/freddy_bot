from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import Page, async_playwright

from freddy_bot.ai.reply_service import ask_ai_reply, ask_manual_reply
from freddy_bot.app.bot_prevention import prevent_repeated_long_message_bot
from freddy_bot.app.records import build_prompt_record
from freddy_bot.app.state import WatchMode, WatchState
from freddy_bot.browser.dom import extract_chat_messages
from freddy_bot.browser.page_finder import ensure_target_page, find_target_page
from freddy_bot.browser.sender import send_reply
from freddy_bot.chat.models import ChatMessage
from freddy_bot.chat.parsing import (
    looks_like_own_timestamped_message,
    parse_own_directed_message,
)
from freddy_bot.chat.prompt_detection import (
    is_prompt_for_nickname,
    is_recent_sent_reply_echo,
)
from freddy_bot.chat.reply_formatting import address_reply
from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger
from freddy_bot.memory.chat_context import append_chat_context, append_direct_context
from freddy_bot.memory.jsonl_store import append_jsonl, clear_reply, read_reply, write_json
from freddy_bot.memory.user_memory import has_user_memory
from freddy_bot.utils import utc_now


async def watch(
    config: WatcherConfig,
    send_replies: bool,
    manual_replies: bool,
    codex_replies: bool,
    auto_send_ai: bool,
    logger: Logger,
) -> None:
    mode = WatchMode(
        send_replies=send_replies,
        manual_replies=manual_replies,
        codex_replies=codex_replies,
        auto_send_ai=auto_send_ai,
    )
    state = WatchState()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(config.cdp_url)
        page = await find_target_page(browser, config.target_url_contains)
        log_startup(config, mode, page, logger)

        while True:
            page = await ensure_target_page(
                browser, page, config.target_url_contains, logger
            )
            messages = await extract_chat_messages(page, config.message_selectors)
            for message in messages:
                page = await process_message(
                    browser, page, config, mode, state, message, logger
                )

            page = await process_pending_file_reply(
                browser, page, config, mode, state, logger
            )
            await asyncio.sleep(config.poll_interval_seconds)


def log_startup(
    config: WatcherConfig, mode: WatchMode, page: Page, logger: Logger
) -> None:
    logger.write(f"Connected to: {page.url}")
    logger.write(f"Watching for messages starting with: {config.nickname}")
    logger.write(f"Reply inbox: {config.reply_inbox}")
    logger.write(f"Log file: {config.log_file}")
    if mode.codex_replies:
        logger.write("Codex replies are ENABLED.")
        if mode.auto_send_ai:
            logger.write("Codex replies will be sent automatically.")
        else:
            logger.write("Codex replies require terminal confirmation.")
    elif mode.manual_replies:
        logger.write("Manual terminal replies are ENABLED.")
    elif mode.send_replies:
        logger.write("Reply sending is ENABLED. Non-empty reply inbox text will be sent.")
    else:
        logger.write("Reply sending is disabled. Use --send-replies to enable it.")
    logger.write("Press Ctrl+C to stop.")


async def process_message(
    browser: Any,
    page: Page,
    config: WatcherConfig,
    mode: WatchMode,
    state: WatchState,
    message: ChatMessage,
    logger: Logger,
) -> Page:
    text = message.text
    if await prevent_repeated_long_message_bot(page, config, state, message, logger):
        return page

    if text in state.seen:
        return page
    state.seen.add(text)

    own_directed = parse_own_directed_message(text, config.nickname)
    if should_ignore_message(config, state, text, own_directed, logger):
        return page

    if own_directed:
        handle_own_directed_message(config, state, message, own_directed, logger)
        return page

    if not append_chat_context(config, message):
        return page

    if not is_prompt_for_nickname(text, config.nickname):
        return page

    state.active_prompt = capture_prompt(config, message, page.url, state, logger)
    if mode.manual_replies or mode.codex_replies:
        page = await handle_interactive_reply(browser, page, config, mode, state, logger)
        state.active_prompt = None
    return page


def should_ignore_message(
    config: WatcherConfig,
    state: WatchState,
    text: str,
    own_directed: tuple[str, str] | None,
    logger: Logger,
) -> bool:
    if (
        config.ignore_own_timestamped_messages
        and looks_like_own_timestamped_message(text, config.nickname)
        and not own_directed
    ):
        logger.write(f"Ignored own timestamped message: {text}", "dim")
        return True

    if is_recent_sent_reply_echo(text, config.nickname, state.sent_replies):
        logger.write(f"Ignored recent sent reply echo: {text}", "dim")
        return True

    return False


def handle_own_directed_message(
    config: WatcherConfig,
    state: WatchState,
    message: ChatMessage,
    own_directed: tuple[str, str],
    logger: Logger,
) -> None:
    target, body = own_directed
    if target in state.known_partners or has_user_memory(config, target):
        append_chat_context(config, message)
        logger.write(f"Saved your message to {target}: {body}", "magenta")
        return

    logger.write(
        f"Ignored first outbound message to untracked {target}: {body}",
        "dim",
    )


def capture_prompt(
    config: WatcherConfig,
    message: ChatMessage,
    source_url: str,
    state: WatchState,
    logger: Logger,
) -> dict[str, Any]:
    if message.username:
        state.known_partners.add(message.username)

    prompt = build_prompt_record(message, source_url)
    append_jsonl(config.output_jsonl, prompt)
    append_jsonl(config.history_jsonl, prompt)
    write_json(config.latest_prompt_json, prompt)

    sender = f" from {message.username}" if message.username else ""
    logger.write(f"Captured prompt [{prompt['id']}]{sender}: {message.text}", "cyan")
    return prompt


async def handle_interactive_reply(
    browser: Any,
    page: Page,
    config: WatcherConfig,
    mode: WatchMode,
    state: WatchState,
    logger: Logger,
) -> Page:
    prompt = state.active_prompt
    if not prompt:
        return page

    if mode.codex_replies:
        reply = await ask_ai_reply(
            config, prompt, logger, mode.auto_send_ai, page, state.seen, state.sent_replies
        )
    else:
        reply = await ask_manual_reply(prompt, logger)

    if not reply:
        record_skipped_reply(config, prompt, page.url, logger)
        return page

    return await record_and_maybe_send_reply(
        browser, page, config, state, prompt, reply, send_to_page=True, logger=logger
    )


async def process_pending_file_reply(
    browser: Any,
    page: Page,
    config: WatcherConfig,
    mode: WatchMode,
    state: WatchState,
    logger: Logger,
) -> Page:
    if mode.manual_replies or mode.codex_replies:
        return page

    reply = read_reply(config.reply_inbox)
    if not reply or not state.active_prompt:
        return page

    page = await record_and_maybe_send_reply(
        browser,
        page,
        config,
        state,
        state.active_prompt,
        reply,
        send_to_page=mode.send_replies,
        logger=logger,
    )
    clear_reply(config.reply_inbox)
    state.active_prompt = None
    return page


async def record_and_maybe_send_reply(
    browser: Any,
    page: Page,
    config: WatcherConfig,
    state: WatchState,
    prompt: dict[str, Any],
    reply: str,
    send_to_page: bool,
    logger: Logger,
) -> Page:
    final_reply = address_reply(reply, prompt.get("username"))
    reply_record = {
        "id": prompt["id"],
        "replied_at": utc_now(),
        "prompt": prompt["text"],
        "reply": final_reply,
        "reply_body": reply,
        "reply_partner": prompt.get("username"),
        "source_url": page.url,
        "status": "reply_sent" if send_to_page else "reply_ready",
    }

    if send_to_page:
        page = await ensure_target_page(browser, page, config.target_url_contains, logger)
        sent = await send_reply(page, config, final_reply, logger)
        if sent:
            remember_sent_reply(config, state, prompt, final_reply)
            logger.write(f"Sent reply for [{prompt['id']}]: {final_reply}", "green")
        else:
            reply_record["status"] = "reply_send_failed"
    else:
        logger.write(f"Reply ready for [{prompt['id']}]: {reply}")

    append_jsonl(config.history_jsonl, reply_record)
    return page


def remember_sent_reply(
    config: WatcherConfig,
    state: WatchState,
    prompt: dict[str, Any],
    final_reply: str,
) -> None:
    state.sent_replies.append(final_reply)
    state.sent_replies = state.sent_replies[-config.ignore_recent_sent_replies :]

    if prompt.get("username"):
        partner = str(prompt["username"])
        state.known_partners.add(partner)
        append_direct_context(config, partner, config.nickname, final_reply)


def record_skipped_reply(
    config: WatcherConfig, prompt: dict[str, Any], source_url: str, logger: Logger
) -> None:
    append_jsonl(
        config.history_jsonl,
        {
            "id": prompt["id"],
            "skipped_at": utc_now(),
            "prompt": prompt["text"],
            "source_url": source_url,
            "status": "reply_skipped",
        },
    )
    logger.write(f"Skipped reply for [{prompt['id']}].")
