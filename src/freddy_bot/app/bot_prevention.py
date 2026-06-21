from __future__ import annotations

import re
from datetime import datetime, timedelta

from playwright.async_api import Page

from freddy_bot.browser.user_actions import ignore_user_from_message
from freddy_bot.chat.models import ChatMessage
from freddy_bot.chat.parsing import normalize_message
from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger
from freddy_bot.app.state import WatchState


async def prevent_repeated_long_message_bot(
    page: Page,
    config: WatcherConfig,
    state: WatchState,
    message: ChatMessage,
    logger: Logger,
) -> bool:
    if not config.bot_prevention_enabled:
        return False

    username = message.username
    if not username or username == config.nickname or username in state.ignored_users:
        return False
    if is_ignore_attempt_on_cooldown(state, username):
        return False
    if config.bot_prevention_guest_rank_only and message.user_rank not in (0, None):
        return False

    if message.dom_id:
        if message.dom_id in state.bot_prevention_seen_dom_ids:
            return False
        state.bot_prevention_seen_dom_ids.add(message.dom_id)

    normalized = normalize_message(message.text)
    if len(normalized) < config.bot_prevention_min_message_chars:
        return False
    if looks_like_aggregate_chat_block(normalized):
        return False

    score = spam_score(normalized)
    if score >= config.bot_prevention_immediate_score:
        logger.write(
            f"High-confidence spam detected from {username} "
            f"(score {score}); attempting ignore.",
            "red",
        )
        ignored = await ignore_user_from_message(page, config, message, logger)
        if ignored:
            state.ignored_users.add(username)
        else:
            state.failed_ignore_attempts[username] = datetime.now()
        return ignored

    if score < config.bot_prevention_repeat_score:
        return False

    signature = f"{username}\n{normalized}"
    repeat_count = state.long_message_repeats.get(signature, 0) + 1
    state.long_message_repeats[signature] = repeat_count

    if repeat_count < config.bot_prevention_repeated_count:
        logger.write(
            f"Long message seen from {username}; waiting for repeat "
            f"({repeat_count}/{config.bot_prevention_repeated_count}).",
            "dim",
        )
        return False

    logger.write(
        f"Repeated long message detected from {username}; attempting ignore.",
        "red",
    )
    ignored = await ignore_user_from_message(page, config, message, logger)
    if ignored:
        state.ignored_users.add(username)
    else:
        state.failed_ignore_attempts[username] = datetime.now()
    return ignored


def looks_like_aggregate_chat_block(text: str) -> bool:
    timestamp_count = len(re.findall(r"\b\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}\b", text))
    if timestamp_count > 1:
        return True

    if text.count(" | ") > 3:
        return True

    lowered = text.lower()
    return " | action | " in lowered or " | video chat" in lowered


def spam_score(text: str) -> int:
    if not text:
        return 0

    score = 0
    characters = [char for char in text if not char.isspace()]
    if not characters:
        return 0

    counts: dict[str, int] = {}
    for char in characters:
        counts[char] = counts.get(char, 0) + 1

    dominant_char, dominant_count = max(counts.items(), key=lambda item: item[1])
    dominant_ratio = dominant_count / len(characters)
    unique_ratio = len(counts) / len(characters)

    if dominant_ratio >= 0.75 and len(characters) >= 120:
        score += 7
    elif dominant_ratio >= 0.5 and len(characters) >= 180:
        score += 4

    if unique_ratio <= 0.08 and len(characters) >= 120:
        score += 3

    if dominant_count >= 80 and not dominant_char.isalnum():
        score += 3

    if "﷽" in text:
        score += 5

    if has_long_repeated_run(text):
        score += 4

    return score


def has_long_repeated_run(text: str, limit: int = 20) -> bool:
    previous = ""
    count = 0
    for char in text:
        if char == previous:
            count += 1
        else:
            previous = char
            count = 1
        if count >= limit:
            return True
    return False


def is_ignore_attempt_on_cooldown(
    state: WatchState, username: str, cooldown_seconds: int = 30
) -> bool:
    last_attempt = state.failed_ignore_attempts.get(username)
    if not last_attempt:
        return False
    return datetime.now() - last_attempt < timedelta(seconds=cooldown_seconds)
