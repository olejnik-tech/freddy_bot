from __future__ import annotations

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from freddy_bot.browser.page_finder import find_target_page
from freddy_bot.chat.parsing import normalize_message
from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger


async def inspect(config: WatcherConfig, limit: int) -> None:
    logger = Logger(config.log_file)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(config.cdp_url)
        page = await find_target_page(browser, config.target_url_contains)

        logger.write(f"Connected to: {page.url}")
        for selector in config.message_selectors:
            elements = []
            for target in [page, *page.frames]:
                try:
                    elements.extend(await target.locator(selector).all())
                except PlaywrightError:
                    continue

            samples: list[str] = []
            for element in elements[-limit:]:
                try:
                    text = normalize_message(await element.inner_text(timeout=300))
                except PlaywrightError:
                    continue
                if text:
                    samples.append(text)

            logger.write(f"\n{selector}: {len(elements)} matches")
            for sample in samples:
                logger.write(f"  - {sample[:240]}")

        logger.write("\nInput selectors:")
        for selector in config.input_selectors:
            count = 0
            for target in [page, *page.frames]:
                try:
                    count += await target.locator(selector).count()
                except PlaywrightError:
                    continue
            logger.write(f"{selector}: {count} matches")

        logger.write("\nInput candidates:")
        candidate_selector = "input, textarea, [contenteditable='true'], button"
        for target_index, target in enumerate([page, *page.frames]):
            try:
                candidates = await target.locator(candidate_selector).all()
            except PlaywrightError:
                continue

            for candidate in candidates[:80]:
                try:
                    details = await candidate.evaluate(
                        """el => ({
                            tag: el.tagName,
                            id: el.id || "",
                            name: el.getAttribute("name") || "",
                            type: el.getAttribute("type") || "",
                            cls: el.className || "",
                            placeholder: el.getAttribute("placeholder") || "",
                            text: (el.innerText || el.value || "").slice(0, 80),
                            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                        })"""
                    )
                except PlaywrightError:
                    continue

                logger.write(
                    "  "
                    f"frame={target_index} tag={details['tag']} id={details['id']} "
                    f"name={details['name']} type={details['type']} "
                    f"class={details['cls']} placeholder={details['placeholder']} "
                    f"visible={details['visible']} text={details['text']}"
                )
