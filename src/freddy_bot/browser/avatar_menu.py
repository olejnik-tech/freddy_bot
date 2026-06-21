from __future__ import annotations

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Page


async def click_avatar_action(page: Page) -> bool:
    for target in avatar_menu_targets(page):
        if await click_avatar_action_in_target(target):
            return True
    return False


async def collect_avatar_menu_text(page: Page) -> str:
    for target in avatar_menu_targets(page):
        try:
            values = await target.evaluate(
                """() => {
                    const roots = Array.from(document.querySelectorAll(
                        '.avother.card_menu, .avother, .card_menu, .bottomcard'
                    ));
                    return roots.flatMap(root => Array.from(root.querySelectorAll('*'))
                        .filter(el => {
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            return rect.width && rect.height &&
                                style.visibility !== 'hidden' &&
                                style.display !== 'none';
                        })
                        .map(el => (el.innerText || el.textContent || '').trim())
                        .filter(Boolean)
                    ).slice(-20);
                }"""
            )
        except PlaywrightError:
            continue
        if values:
            return " | ".join(str(value) for value in values)
    return ""


def avatar_menu_targets(page: Page) -> list[Page | Frame]:
    return [page, *page.frames]


async def click_avatar_action_in_target(target: Page | Frame) -> bool:
    try:
        clicked = await target.evaluate(
            """() => {
                const selectors = [
                    '.avother.card_menu .get_actions.avactions',
                    '.avother .get_actions.avactions',
                    '.card_menu .get_actions.avactions',
                    '.bottomcard .get_actions.avactions',
                    '.get_actions.avactions'
                ];

                const candidates = selectors.flatMap(selector =>
                    Array.from(document.querySelectorAll(selector))
                ).filter(el => {
                    const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return text.includes('action') &&
                        rect.width && rect.height &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none';
                });

                const target = candidates[0];
                if (!target) {
                    return false;
                }
                target.click();
                return true;
            }"""
        )
    except PlaywrightError:
        return False

    return bool(clicked)
