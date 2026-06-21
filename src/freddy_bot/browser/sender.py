from __future__ import annotations

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page

from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger


async def find_first_visible(page: Page, selectors: tuple[str, ...]) -> Locator | None:
    targets: list[Page | Frame] = [page, *page.frames]
    for selector in selectors:
        for target in targets:
            try:
                locator = target.locator(selector).last
                if await locator.count() and await locator.is_visible(timeout=300):
                    return locator
            except PlaywrightError:
                continue
    return None

async def send_reply(page: Page, config: WatcherConfig, reply: str, logger: Logger) -> bool:
    if page.is_closed():
        logger.write("Cannot send reply: the chat page target is closed.")
        return False

    input_locator = await find_first_visible(page, config.input_selectors)
    if input_locator is None:
        try:
            await page.keyboard.type(reply)
            await page.keyboard.press("Enter")
            logger.write("Sent reply using focused-element keyboard fallback.")
            return True
        except PlaywrightError as error:
            logger.write(f"Could not send reply using keyboard fallback: {error}")
            return False

    try:
        await input_locator.fill(reply)

        if config.send_with_enter:
            await input_locator.press("Enter")
            return True

        button = await find_first_visible(page, config.send_button_selectors)
        if button is None:
            logger.write(
                "Could not find a visible send button. Tune send_button_selectors in config.json."
            )
            return False
        await button.click()
        return True
    except PlaywrightError as error:
        logger.write(f"Could not send reply through chat input: {error}")
        return False
