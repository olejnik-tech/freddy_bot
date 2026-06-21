from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from freddy_bot.logging import Logger


async def find_target_page(browser: Any, target_url_contains: str) -> Page:
    pages: list[Page] = []
    for context in browser.contexts:
        pages.extend(page for page in context.pages if not page.is_closed())

    for page in pages:
        if target_url_contains in page.url:
            return page

    if pages:
        page_list = "\n".join(f"- {page.url}" for page in pages)
        raise RuntimeError(
            f"No open page URL contains {target_url_contains!r}.\n"
            f"Open pages:\n{page_list}"
        )

    raise RuntimeError("Connected to browser, but no pages are open.")

async def ensure_target_page(
    browser: Any,
    page: Page,
    target_url_contains: str,
    logger: Logger,
) -> Page:
    if not page.is_closed() and target_url_contains in page.url:
        return page

    logger.write("Refreshing browser page handle.")
    return await find_target_page(browser, target_url_contains)
