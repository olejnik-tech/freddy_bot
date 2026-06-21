from __future__ import annotations

from playwright.async_api import async_playwright

from freddy_bot.browser.brave import start_brave
from freddy_bot.browser.cdp import wait_for_cdp
from freddy_bot.browser.page_finder import ensure_target_page, find_target_page
from freddy_bot.browser.sender import send_reply
from freddy_bot.app.watcher import watch
from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger


async def send_once(config: WatcherConfig, text: str) -> None:
    logger = Logger(config.log_file)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(config.cdp_url)
        page = await find_target_page(browser, config.target_url_contains)
        page = await ensure_target_page(browser, page, config.target_url_contains, logger)
        sent = await send_reply(page, config, text, logger)
        if sent:
            logger.write(f"Sent: {text}")
        else:
            logger.write(f"Send failed: {text}")

async def run_all(
    config: WatcherConfig,
    wait_seconds: float,
    codex_replies: bool,
    manual_replies: bool,
    auto_send_ai: bool,
) -> None:
    logger = Logger(config.log_file)
    if config.last_codex_prompt_file.exists():
        config.last_codex_prompt_file.write_text("", encoding="utf-8")
    start_brave(config, logger)
    logger.write("Log in or enter the chat in Brave if needed.")
    await wait_for_cdp(config.cdp_url, wait_seconds, logger)
    await watch(
        config,
        send_replies=False,
        manual_replies=manual_replies,
        codex_replies=codex_replies,
        auto_send_ai=auto_send_ai,
        logger=logger,
    )
