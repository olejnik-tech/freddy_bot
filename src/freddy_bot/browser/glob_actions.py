from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Page


async def click_glob_actions_text(page: Page, labels: tuple[str, ...]) -> bool:
    for target in glob_action_targets(page):
        if await click_glob_actions_text_in_target(target, labels):
            return True
    return False


async def click_exact_ignore_sub_list_content(page: Page) -> bool:
    for target in glob_action_targets(page):
        if await click_exact_ignore_sub_list_content_in_target(target):
            return True
    return False


async def wait_for_ignore_item(page: Page, timeout_seconds: float = 2.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if await has_ignore_item(page):
            return True
        await asyncio.sleep(0.1)
    return False


def glob_action_targets(page: Page) -> list[Page | Frame]:
    return [page, *page.frames]


async def has_ignore_item(page: Page) -> bool:
    for target in glob_action_targets(page):
        try:
            found = await target.evaluate(
                """() => {
                    const root = document.querySelector('#glob_actions');
                    if (!root) {
                        return !!document.querySelector('#ignore_private, [name="acu_ignore"]');
                    }
                    return Array.from(root.querySelectorAll('.sub_list_content, *'))
                        .some(el => (el.innerText || el.textContent || '').trim().toLowerCase() === 'ignore');
                }"""
            )
        except PlaywrightError:
            continue
        if found:
            return True
    return False


async def click_glob_actions_text_in_target(
    target: Page | Frame, labels: tuple[str, ...]
) -> bool:
    try:
        clicked = await target.evaluate(
            """labels => {
                const root = document.querySelector('#glob_actions');
                if (!root) {
                    return false;
                }

                const normalizedLabels = labels.map(label => label.toLowerCase());
                const candidates = Array.from(root.querySelectorAll('*'))
                    .filter(el => {
                        const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                        if (!normalizedLabels.includes(text)) {
                            return false;
                        }
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width && rect.height &&
                            style.visibility !== 'hidden' &&
                            style.display !== 'none';
                    })
                    .sort((left, right) =>
                        left.getBoundingClientRect().width * left.getBoundingClientRect().height -
                        right.getBoundingClientRect().width * right.getBoundingClientRect().height
                    );

                const target = candidates[0];
                if (!target) {
                    return false;
                }
                target.click();
                return true;
            }""",
            list(labels),
        )
    except PlaywrightError:
        return False

    return bool(clicked)


async def click_exact_ignore_sub_list_content_in_target(target: Page | Frame) -> bool:
    try:
        clicked = await target.evaluate(
            """() => {
                const root = document.querySelector('#glob_actions');
                if (!root) {
                    return false;
                }

                const candidates = Array.from(root.querySelectorAll('.sub_list_content'))
                    .filter(el => {
                        const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return text === 'ignore' &&
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
