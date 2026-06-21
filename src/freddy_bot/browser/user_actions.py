from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Page

from freddy_bot.browser.avatar_menu import (
    click_avatar_action,
    collect_avatar_menu_text,
)
from freddy_bot.browser.avatar_click import (
    click_avatar_by_username,
    click_chat_avenue_avatar,
    click_user_target_from_ancestors,
)
from freddy_bot.browser.glob_actions import (
    click_exact_ignore_sub_list_content,
    click_glob_actions_text,
    wait_for_ignore_item,
)
from freddy_bot.chat.models import ChatMessage
from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger


async def ignore_user_from_message(
    page: Page,
    config: WatcherConfig,
    message: ChatMessage,
    logger: Logger,
) -> bool:
    if message.element is None:
        logger.write("Cannot ignore user: message DOM element is unavailable.", "red")
        return False

    if await ignore_user_directly(page, message):
        logger.write(f"Ignored suspected spam user: {message.username or 'unknown'}", "red")
        await refresh_after_ignore(page, logger)
        return True

    if not await open_user_menu(page, message, config.user_menu_selectors):
        logger.write("Could not open user menu for spam message.", "red")
        details = await describe_message_avatar_target(message)
        if details:
            logger.write(details, "dim")
        return False

    await asyncio.sleep(0.5)
    action_clicked = await click_action_menu(page, config.user_action_selectors)
    if not action_clicked:
        logger.write("Could not click Action in user menu.", "red")
        menu_text = await collect_avatar_menu_text(page)
        if menu_text:
            logger.write(f"Visible avatar menu candidates: {menu_text}", "dim")
        return False
    await wait_for_ignore_item(page, timeout_seconds=3.0)
    if not await click_ignore_menu_item(page, config.user_ignore_selectors):
        logger.write("Could not find Ignore/Block action in user menu.", "red")
        menu_text = await collect_visible_menu_text(page)
        if menu_text:
            logger.write(f"Visible menu candidates: {menu_text}", "dim")
        return False

    logger.write(f"Ignored suspected spam user: {message.username or 'unknown'}", "red")
    await refresh_after_ignore(page, logger)
    return True


async def ignore_user_directly(page: Page, message: ChatMessage) -> bool:
    user_id = await resolve_message_user_id(message)
    if not user_id:
        return False

    for target in [page, *page.frames]:
        try:
            ignored = await target.evaluate(
                """async userId => {
                    const target = String(userId || '').trim();
                    if (!/^\\d+$/.test(target)) {
                        return false;
                    }

                    const path = 'system/action/action_member.php';
                    if (typeof window.$ === 'function' && typeof window.$.post === 'function') {
                        await new Promise(resolve => {
                            window.$.post(path, {
                                acu_ignore: 1,
                                target
                            }).always(resolve);
                        });
                    }
                    else {
                        const body = new URLSearchParams({
                            acu_ignore: '1',
                            target
                        });
                        await fetch(path, {
                            method: 'POST',
                            credentials: 'same-origin',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body
                        });
                    }

                    const numericTarget = parseInt(target, 10);
                    if (window.ignoreList && typeof window.ignoreList.add === 'function') {
                        window.ignoreList.add(numericTarget);
                    }
                    if (typeof window.addIgnore === 'function') {
                        window.addIgnore(numericTarget);
                    }
                    return true;
                }""",
                user_id,
            )
        except PlaywrightError:
            continue

        if ignored:
            return True

    return False


async def resolve_message_user_id(message: ChatMessage) -> str | None:
    if message.user_id and message.user_id.isdigit():
        return message.user_id
    if message.element is None:
        return None

    try:
        value = await message.element.evaluate(
            """el => {
                const row = el.closest('li.chat_log, li[class*="chat_log"]');
                const avatar = row ? row.querySelector('.chat_avatar') : null;
                return (avatar && avatar.getAttribute('data-id')) ||
                    (row && row.getAttribute('data-user')) ||
                    '';
            }"""
        )
    except PlaywrightError:
        return None

    user_id = str(value or "").strip()
    if user_id.isdigit():
        return user_id
    return None


async def open_user_menu(
    page: Page, message: ChatMessage, user_menu_selectors: tuple[str, ...]
) -> bool:
    message_element = message.element
    if message_element is None:
        return False

    if await click_chat_avenue_avatar(page, message_element, message.username):
        return True

    if await click_avatar_by_username(page, message.username):
        return True

    for selector in user_menu_selectors:
        try:
            target = message_element.locator(selector).first
            if await target.count() and await target.is_visible(timeout=300):
                await target.click(timeout=1000)
                return True
        except PlaywrightError:
            continue

    if await click_user_target_from_ancestors(message_element, user_menu_selectors):
        return True

    return False


async def click_action_menu(page: Page, selectors: tuple[str, ...]) -> bool:
    if await click_avatar_action(page):
        await asyncio.sleep(0.5)
        return True
    if await click_first_visible(page, (".get_actions.avactions", ".avactions")):
        await asyncio.sleep(0.5)
        return True
    if await click_glob_actions_text(page, ("Action", "Actions")):
        await asyncio.sleep(0.5)
        return True
    clicked = await click_first_visible(page, selectors)
    if clicked:
        await asyncio.sleep(0.5)
    return clicked


async def click_ignore_menu_item(page: Page, selectors: tuple[str, ...]) -> bool:
    if await click_first_visible(page, ("#ignore_private", "[name='acu_ignore']")):
        await asyncio.sleep(0.5)
        return True
    if await click_exact_ignore_sub_list_content(page):
        await asyncio.sleep(0.5)
        return True
    if await click_glob_actions_text(page, ("Ignore",)):
        await asyncio.sleep(0.5)
        return True
    return await click_first_visible(page, selectors)


async def click_first_visible(page: Page, selectors: tuple[str, ...]) -> bool:
    targets: list[Page | Frame] = [page, *page.frames]
    for selector in selectors:
        for target in targets:
            try:
                locators = await target.locator(selector).all()
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
    return False


async def refresh_after_ignore(page: Page, logger: Logger) -> None:
    try:
        await page.reload(wait_until="domcontentloaded", timeout=10000)
        logger.write("Page refreshed after ignore action.", "yellow")
    except PlaywrightError as error:
        logger.write(f"Ignore succeeded, but page refresh failed: {error}", "red")


async def collect_visible_menu_text(page: Page) -> str:
    try:
        values = await page.evaluate(
            """() => {
                const root = document.querySelector('#private_opt') ||
                    document.querySelector('#glob_actions');
                if (!root) {
                    return [];
                }
                return Array.from(root.querySelectorAll('*'))
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width && rect.height &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none';
                })
                .map(el => (el.innerText || el.textContent || el.getAttribute('title') || '').trim())
                .filter(Boolean)
                .slice(-20);
            }"""
        )
    except PlaywrightError:
        return ""

    return " | ".join(str(value) for value in values)


async def describe_message_avatar_target(message: ChatMessage) -> str:
    if message.element is None:
        return ""
    try:
        details = await message.element.evaluate(
            """el => {
                const row = el.closest('li.chat_log, li[class*="chat_log"]');
                const avatar = row ? row.querySelector('.chat_avatar') : null;
                return {
                    hasRow: !!row,
                    hasAvatar: !!avatar,
                    dataName: avatar ? avatar.getAttribute('data-name') : '',
                    dataId: avatar ? avatar.getAttribute('data-id') : '',
                    dataRank: avatar ? avatar.getAttribute('data-rank') : ''
                };
            }"""
        )
    except Exception:
        return ""

    return (
        "Avatar target debug: "
        f"username={message.username!r} user_id={message.user_id!r} "
        f"rank={message.user_rank!r} row={details.get('hasRow')} "
        f"avatar={details.get('hasAvatar')} data_name={details.get('dataName')!r} "
        f"data_id={details.get('dataId')!r} data_rank={details.get('dataRank')!r}"
    )
