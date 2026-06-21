from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page


async def click_user_target_from_ancestors(
    message_element: Locator, selectors: tuple[str, ...]
) -> bool:
    try:
        clicked = await message_element.evaluate(
            """(el, selectors) => {
                let current = el;
                for (let depth = 0; current && depth < 8; depth++, current = current.parentElement) {
                    for (const selector of selectors) {
                        const target = current.matches(selector)
                            ? current
                            : current.querySelector(selector);
                        if (!target) {
                            continue;
                        }

                        const rect = target.getBoundingClientRect();
                        if (!rect.width || !rect.height) {
                            continue;
                        }

                        target.dispatchEvent(new MouseEvent('mouseover', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));
                        target.dispatchEvent(new MouseEvent('mousedown', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            button: 0
                        }));
                        target.dispatchEvent(new MouseEvent('mouseup', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            button: 0
                        }));
                        target.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            button: 0
                        }));
                        return true;
                    }
                }
                return false;
            }""",
            list(selectors),
        )
    except PlaywrightError:
        return False

    if clicked:
        await asyncio.sleep(0.5)
    return bool(clicked)


async def click_chat_avenue_avatar(
    page: Page, message_element: Locator, username: str | None
) -> bool:
    if await click_avatar_point_from_message(page, message_element):
        return True

    exact_selectors = (
        "xpath=ancestor::li[contains(@class, 'chat_log')][1]//div[contains(@class, 'avtrig') and contains(@class, 'chat_avatar')]",
        "xpath=ancestor::li[contains(@class, 'chat_log')][1]//img[contains(@class, 'cavatar')]",
        "xpath=ancestor::li[contains(@class, 'chat_log')][1]//img[contains(@class, 'avav')]",
    )
    for selector in exact_selectors:
        try:
            locators = await message_element.locator(selector).all()
        except PlaywrightError:
            continue

        for locator in locators:
            try:
                if not await locator.is_visible(timeout=300):
                    continue
                await locator.click(timeout=1000)
                await asyncio.sleep(0.5)
                return True
            except PlaywrightError:
                continue

    return await click_avatar_from_ancestor_dom(message_element, username)


async def click_avatar_point_from_message(page: Page, message_element: Locator) -> bool:
    try:
        point = await message_element.evaluate(
            """el => {
                const row = el.closest('li.chat_log, li[class*="chat_log"]');
                if (!row) {
                    return null;
                }

                const avatar = row.querySelector('div.avtrig.chat_avatar, div.avs_menu.chat_avatar, img.cavatar, img.avav');
                if (!avatar) {
                    return null;
                }

                const rect = avatar.getBoundingClientRect();
                const style = window.getComputedStyle(avatar);
                if (!rect.width || !rect.height ||
                    style.visibility === 'hidden' ||
                    style.display === 'none') {
                    return null;
                }

                return {
                    x: rect.left + rect.width / 2,
                    y: rect.top + rect.height / 2
                };
            }"""
        )
    except PlaywrightError:
        return False

    if not point:
        return False

    try:
        await page.mouse.click(float(point["x"]), float(point["y"]))
        await asyncio.sleep(0.5)
        return True
    except PlaywrightError:
        return False


async def click_avatar_from_ancestor_dom(
    message_element: Locator, username: str | None
) -> bool:
    try:
        clicked = await message_element.evaluate(
            """(el, username) => {
                const avatarSelectors = [
                    'div.avtrig.chat_avatar',
                    'div.avs_menu.chat_avatar',
                    'img.cavatar',
                    'img.avav',
                    'div[class*="avtrig"][class*="chat_avatar"]',
                    'img[class*="cavatar"]',
                    'img[class*="avav"]'
                ];

                function visible(node) {
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width && rect.height &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none';
                }

                function clickNode(node) {
                    node.dispatchEvent(new MouseEvent('mouseover', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    }));
                    node.dispatchEvent(new MouseEvent('mousedown', {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        button: 0
                    }));
                    node.dispatchEvent(new MouseEvent('mouseup', {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        button: 0
                    }));
                    node.dispatchEvent(new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        button: 0
                    }));
                }

                let current = el;
                for (let depth = 0; current && depth < 10; depth++, current = current.parentElement) {
                    for (const selector of avatarSelectors) {
                        const avatar = current.matches(selector)
                            ? current
                            : current.querySelector(selector);
                        if (avatar && visible(avatar)) {
                            clickNode(avatar);
                            return true;
                        }
                    }
                }
                return false;
            }""",
            username,
        )
    except PlaywrightError:
        return False

    if clicked:
        await asyncio.sleep(0.5)
    return bool(clicked)


async def click_avatar_by_username(page: Page, username: str | None) -> bool:
    if not username:
        return False

    targets: list[Page | Frame] = [page, *page.frames]
    for target in targets:
        try:
            point = await target.evaluate(
                """username => {
                    const names = new Set([
                        username,
                        username.replace(/^@/, '')
                    ].map(value => value.toLowerCase()));

                    const avatars = Array.from(document.querySelectorAll(
                        'div.avtrig.chat_avatar, div.avs_menu.chat_avatar'
                    ));
                    for (const avatar of avatars) {
                        const dataName = (avatar.getAttribute('data-name') || '').toLowerCase();
                        if (!names.has(dataName)) {
                            continue;
                        }
                        const rect = avatar.getBoundingClientRect();
                        const style = window.getComputedStyle(avatar);
                        if (!rect.width || !rect.height ||
                            style.visibility === 'hidden' ||
                            style.display === 'none') {
                            continue;
                        }
                        return {
                            x: rect.left + rect.width / 2,
                            y: rect.top + rect.height / 2
                        };
                    }
                    return null;
                }""",
                username,
            )
        except PlaywrightError:
            continue

        if not point:
            continue

        try:
            await page.mouse.click(float(point["x"]), float(point["y"]))
            await asyncio.sleep(0.5)
            return True
        except PlaywrightError:
            continue

    return False
