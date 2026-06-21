from __future__ import annotations

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page

from freddy_bot.chat.models import ChatMessage
from freddy_bot.chat.parsing import normalize_message


async def extract_message_texts(page: Page, selectors: tuple[str, ...]) -> list[str]:
    return [message.text for message in await extract_chat_messages(page, selectors)]

async def extract_chat_messages(page: Page, selectors: tuple[str, ...]) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    seen_element_ids: set[str] = set()
    targets: list[Page | Frame] = [page, *page.frames]
    for selector in selectors:
        for target in targets:
            try:
                elements = await target.locator(selector).all()
            except PlaywrightError:
                continue

            for element in elements:
                try:
                    dom_id = str(
                        await element.evaluate(
                            """el => {
                                if (!el.dataset.freddyBotDomId) {
                                    el.dataset.freddyBotDomId =
                                        crypto.randomUUID ? crypto.randomUUID() :
                                        `${Date.now()}-${Math.random()}`;
                                }
                                return el.dataset.freddyBotDomId;
                            }"""
                        )
                    )
                    text = normalize_message(await element.inner_text(timeout=300))
                except PlaywrightError:
                    continue
                if not text or dom_id in seen_element_ids:
                    continue
                seen_element_ids.add(dom_id)
                username = await extract_username_from_element(element)
                user_meta = await extract_user_meta_from_element(element)
                messages.append(
                    ChatMessage(
                        text=text,
                        username=username,
                        user_id=user_meta.get("user_id"),
                        user_rank=user_meta.get("user_rank"),
                        dom_id=dom_id,
                        element=element,
                    )
                )
    return messages

async def extract_username_from_element(element: Locator) -> str | None:
    try:
        value = await element.evaluate(
            """el => {
                const selectors = [
                    '.username', '.user_name', '.chat_username', '.uname',
                    '.name', '.my_name', '[class*="username"]',
                    '[class*="user-name"]', '[class*="user"] [class*="name"]'
                ];

                let current = el;
                for (let depth = 0; current && depth < 5; depth++, current = current.parentElement) {
                    for (const selector of selectors) {
                        const found = current.querySelector(selector);
                        if (found && found.innerText) {
                            return found.innerText.trim();
                        }
                    }

                    const dataName = current.getAttribute('data-name') ||
                        current.getAttribute('data-user') ||
                        current.getAttribute('data-username');
                    if (dataName) {
                        return dataName.trim();
                    }
                }
                return '';
            }"""
        )
    except PlaywrightError:
        return None

    username = normalize_message(str(value))
    if not username or len(username) > 40:
        return None
    return username


async def extract_user_meta_from_element(element: Locator) -> dict[str, str | int | None]:
    try:
        value = await element.evaluate(
            """el => {
                const row = el.closest('li.chat_log, li[class*="chat_log"]');
                const avatar = row ? row.querySelector('.chat_avatar') : null;
                if (avatar) {
                    return {
                        user_id: avatar.getAttribute('data-id') || '',
                        user_rank: avatar.getAttribute('data-rank') || ''
                    };
                }
                return { user_id: '', user_rank: '' };
            }"""
        )
    except PlaywrightError:
        return {"user_id": None, "user_rank": None}

    raw_rank = str(value.get("user_rank") or "")
    try:
        user_rank: int | None = int(raw_rank)
    except ValueError:
        user_rank = None

    user_id = str(value.get("user_id") or "") or None
    return {"user_id": user_id, "user_rank": user_rank}
