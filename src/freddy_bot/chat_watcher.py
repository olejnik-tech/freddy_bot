from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page, async_playwright


DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass(frozen=True)
class WatcherConfig:
    nickname: str
    cdp_url: str
    target_url_contains: str
    poll_interval_seconds: float
    output_jsonl: Path
    history_jsonl: Path
    latest_prompt_json: Path
    reply_inbox: Path
    chat_context_jsonl: Path
    user_memory_dir: Path
    last_codex_prompt_file: Path
    log_file: Path
    brave_script: Path
    personality_file: Path
    codex_command: tuple[str, ...]
    codex_timeout_seconds: float
    ai_history_context_lines: int
    recent_chat_context_lines: int
    message_selectors: tuple[str, ...]
    input_selectors: tuple[str, ...]
    send_button_selectors: tuple[str, ...]
    send_with_enter: bool
    confirm_codex_replies: bool
    ignore_own_timestamped_messages: bool
    ignore_recent_sent_replies: int

    @classmethod
    def from_file(cls, path: Path) -> "WatcherConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            nickname=str(data.get("nickname", "Freddy_922")),
            cdp_url=str(data.get("cdp_url", "http://127.0.0.1:9222")),
            target_url_contains=str(data.get("target_url_contains", "chat-avenue.com")),
            poll_interval_seconds=float(data.get("poll_interval_seconds", 1.0)),
            output_jsonl=Path(data.get("output_jsonl", "captures/prompts.jsonl")),
            history_jsonl=Path(data.get("history_jsonl", "captures/history.jsonl")),
            latest_prompt_json=Path(
                data.get("latest_prompt_json", "captures/latest_prompt.json")
            ),
            reply_inbox=Path(data.get("reply_inbox", "captures/next_reply.txt")),
            chat_context_jsonl=Path(
                data.get("chat_context_jsonl", "captures/chat_context.jsonl")
            ),
            user_memory_dir=Path(data.get("user_memory_dir", "captures/users")),
            last_codex_prompt_file=Path(
                data.get("last_codex_prompt_file", "captures/last_codex_prompt.txt")
            ),
            log_file=Path(data.get("log_file", "captures/runtime.log")),
            brave_script=Path(
                data.get("brave_script", "scripts/start_brave_debug.ps1")
            ),
            personality_file=Path(data.get("personality_file", "persona_freddy.md")),
            codex_command=tuple(
                data.get(
                    "codex_command",
                    ["codex", "exec", "--ephemeral", "--sandbox", "read-only"],
                )
            ),
            codex_timeout_seconds=float(data.get("codex_timeout_seconds", 90)),
            ai_history_context_lines=int(data.get("ai_history_context_lines", 12)),
            recent_chat_context_lines=int(data.get("recent_chat_context_lines", 30)),
            message_selectors=tuple(data.get("message_selectors", [])),
            input_selectors=tuple(data.get("input_selectors", [])),
            send_button_selectors=tuple(data.get("send_button_selectors", [])),
            send_with_enter=bool(data.get("send_with_enter", True)),
            confirm_codex_replies=bool(data.get("confirm_codex_replies", False)),
            ignore_own_timestamped_messages=bool(
                data.get("ignore_own_timestamped_messages", True)
            ),
            ignore_recent_sent_replies=int(data.get("ignore_recent_sent_replies", 20)),
        )


@dataclass(frozen=True)
class ChatMessage:
    text: str
    username: str | None = None


class Logger:
    COLORS = {
        "reset": "\033[0m",
        "dim": "\033[2m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "magenta": "\033[35m",
        "cyan": "\033[36m",
        "bold": "\033[1m",
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message: str = "", color: str | None = None) -> None:
        timestamped = f"{utc_now()} {message}"
        if color:
            color_code = self.COLORS.get(color, "")
            reset = self.COLORS["reset"] if color_code else ""
            print(f"{color_code}{message}{reset}", flush=True)
        else:
            print(message, flush=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(timestamped + "\n")


def normalize_message(text: str) -> str:
    text = text.replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_prompt_for_nickname(text: str, nickname: str) -> bool:
    normalized = normalize_message(text)
    return normalized.startswith(nickname) and not looks_like_own_timestamped_message(
        normalized, nickname
    )


def looks_like_own_timestamped_message(text: str, nickname: str) -> bool:
    pattern = rf"^{re.escape(nickname)}\s+\d{{1,2}}/\d{{1,2}}\s+\d{{1,2}}:\d{{2}}\b"
    return re.search(pattern, normalize_message(text)) is not None


def parse_own_directed_message(text: str, nickname: str) -> tuple[str, str] | None:
    normalized = normalize_message(text)
    pattern = (
        rf"^{re.escape(nickname)}\s+"
        rf"\d{{1,2}}/\d{{1,2}}\s+\d{{1,2}}:\d{{2}}\s+"
        rf"(?P<target>\S+)\s+(?P<body>.+)$"
    )
    match = re.search(pattern, normalized)
    if not match:
        return None
    return match.group("target"), match.group("body").strip()


def conversation_partner(message: ChatMessage, nickname: str) -> str | None:
    if is_prompt_for_nickname(message.text, nickname):
        return message.username

    own_message = parse_own_directed_message(message.text, nickname)
    if own_message:
        return own_message[0]

    return None


def is_recent_sent_reply_echo(text: str, nickname: str, sent_replies: list[str]) -> bool:
    normalized = normalize_message(text)
    if not normalized.startswith(nickname):
        return False

    return any(reply and reply in normalized for reply in sent_replies)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_id(text: str) -> str:
    digest = hashlib.sha1(f"{utc_now()}:{text}".encode("utf-8")).hexdigest()
    return digest[:12]


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


async def extract_message_texts(page: Page, selectors: tuple[str, ...]) -> list[str]:
    return [message.text for message in await extract_chat_messages(page, selectors)]


async def extract_chat_messages(page: Page, selectors: tuple[str, ...]) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    seen_texts: set[str] = set()
    targets: list[Page | Frame] = [page, *page.frames]
    for selector in selectors:
        for target in targets:
            try:
                elements = await target.locator(selector).all()
            except PlaywrightError:
                continue

            for element in elements:
                try:
                    text = normalize_message(await element.inner_text(timeout=300))
                except PlaywrightError:
                    continue
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                username = await extract_username_from_element(element)
                messages.append(ChatMessage(text=text, username=username))
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


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_reply(path: Path) -> str | None:
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None

    return text


def clear_reply(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def load_personality(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_recent_history(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records[-limit:]


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned[:80] or "unknown"


def append_chat_context(config: WatcherConfig, message: ChatMessage) -> bool:
    partner = conversation_partner(message, config.nickname)
    if not partner:
        return False

    record = {
        "seen_at": utc_now(),
        "username": message.username,
        "partner": partner,
        "text": message.text,
    }
    append_jsonl(config.chat_context_jsonl, record)

    append_user_memory(config, partner, message.text)
    return True


def append_direct_context(
    config: WatcherConfig, partner: str, username: str, text: str
) -> None:
    record = {
        "seen_at": utc_now(),
        "username": username,
        "partner": partner,
        "text": text,
    }
    append_jsonl(config.chat_context_jsonl, record)
    append_user_memory(config, partner, text)


def append_user_memory(config: WatcherConfig, username: str, text: str) -> None:
    config.user_memory_dir.mkdir(parents=True, exist_ok=True)
    path = config.user_memory_dir / f"{safe_filename(username)}.md"
    if not path.exists():
        path.write_text(f"# {username}\n\n## Observed Chat\n\n", encoding="utf-8")

    with path.open("a", encoding="utf-8") as file:
        file.write(f"- {utc_now()}: {text}\n")


def load_user_memory(config: WatcherConfig, username: str | None) -> str:
    if not username:
        return ""

    path = config.user_memory_dir / f"{safe_filename(username)}.md"
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    return "\n".join(lines[-30:])


def has_user_memory(config: WatcherConfig, username: str) -> bool:
    path = config.user_memory_dir / f"{safe_filename(username)}.md"
    return path.exists()


def format_chat_context(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records:
        username = record.get("username") or "unknown"
        partner = record.get("partner") or "unknown"
        text = record.get("text", "")
        if text:
            lines.append(f"with {partner} | {username}: {text}")
    return "\n".join(lines)


def format_partner_transcript(
    records: list[dict[str, Any]], partner: str, nickname: str
) -> str:
    lines: list[str] = []
    for record in records:
        if record.get("partner") != partner:
            continue

        username = record.get("username") or "unknown"
        text = normalize_message(str(record.get("text", "")))
        own_directed = parse_own_directed_message(text, nickname)
        if own_directed:
            _, body = own_directed
            lines.append(f"{nickname}: {body}")
        elif username == partner:
            body = text
            if body.startswith(nickname):
                body = body[len(nickname) :].lstrip(" ,:-")
            lines.append(f"{partner}: {body}")
        elif username == nickname:
            if text.lower().startswith(partner.lower()):
                text = text[len(partner) :].lstrip(" ,:-")
            lines.append(f"{nickname}: {text}")
    return "\n".join(lines[-20:])


def format_history(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records:
        status = record.get("status", "unknown")
        if status == "captured":
            lines.append(f"Incoming: {record.get('text', '')}")
        elif status == "reply_sent":
            lines.append(f"Freddy_922 reply: {record.get('reply', '')}")
        elif status == "reply_skipped":
            lines.append(f"Skipped: {record.get('prompt', '')}")
    return "\n".join(line for line in lines if line.strip())


def build_codex_prompt(config: WatcherConfig, prompt: dict[str, Any]) -> str:
    partner = str(prompt.get("username") or "the person who tagged Freddy_922")
    personality = load_personality(config.personality_file)
    context_records = load_recent_history(
        config.chat_context_jsonl, config.recent_chat_context_lines
    )
    partner_transcript = format_partner_transcript(
        context_records, partner, config.nickname
    )
    current_message = normalize_message(str(prompt["text"]))
    if current_message.startswith(config.nickname):
        current_message = current_message[len(config.nickname) :].lstrip(" ,:-")
    new_context = normalize_message(str(prompt.get("new_context") or ""))

    return f"""Roleplay Freddy_922 and write his next chat reply.

Persona:
{personality or "Friendly, casual, relaxed."}

Who is speaking to Freddy_922: {partner}

Previous conversation with {partner}:
{partner_transcript or "(none captured yet)"}
{f'''
New relevant activity before replying:
{new_context}
''' if new_context else ''}
Current message from {partner}:
{current_message}

Return only the reply body.
Do not include `{partner}` at the start; the script adds that tag.
Answer the current message directly, using the previous conversation if needed.
Do not mention prompts, scripts, Codex, or AI.
"""


def run_codex_reply(config: WatcherConfig, prompt: dict[str, Any]) -> str:
    prompt_text = build_codex_prompt(config, prompt)
    config.last_codex_prompt_file.parent.mkdir(parents=True, exist_ok=True)
    config.last_codex_prompt_file.write_text(prompt_text, encoding="utf-8")

    command = resolve_command([*config.codex_command, prompt_text])
    result = subprocess.run(
        command,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=config.codex_timeout_seconds,
        check=False,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Codex reply generation failed: {error}")

    return result.stdout.strip()


def is_bad_codex_reply(reply: str) -> bool:
    lowered = reply.lower()
    bad_phrases = (
        "send me the",
        "what's the message",
        "what’s the message",
        "whats the message",
        "what message",
        "what should",
        "what is freddy",
        "what freddy",
        "provide the",
        "provide more context",
        "need more context",
        "i need context",
        "what context",
        "chat context",
        "chat message/context",
        "incoming message",
    )
    generic_greetings = (
        "what's up",
        "what’s up",
        "whats up",
        "good to see you",
    )
    return any(phrase in lowered for phrase in bad_phrases) or any(
        phrase in lowered for phrase in generic_greetings
    )


def address_reply(reply: str, partner: str | None) -> str:
    reply = normalize_message(reply)
    if not partner:
        return reply

    reply = re.sub(
        rf"^(hey|hi|hello)\s+{re.escape(partner)}\b[,\s:-]*",
        r"\1 ",
        reply,
        flags=re.IGNORECASE,
    )
    reply = normalize_message(reply)

    if reply.lower().startswith(partner.lower()):
        reply = reply[len(partner) :].lstrip(" ,:-")

    return f"{partner} {reply}"


def is_too_weak_reply(reply: str) -> bool:
    lowered = normalize_message(reply).lower().strip(" .,!?:;")
    words = re.findall(r"[A-Za-z]+", lowered)
    weak_exact = {"got it", "okay", "ok", "sure", "hey", "hello", "hi"}
    weak_phrases = ("what's up", "whats up", "good to see you")
    return lowered in weak_exact or len(words) < 4 or any(
        phrase in lowered for phrase in weak_phrases
    )


def is_invalid_reply_for_prompt(reply: str, prompt: dict[str, Any]) -> bool:
    return is_bad_codex_reply(reply) or is_too_weak_reply(reply)


def fallback_reply_body(prompt: dict[str, Any]) -> str | None:
    return None


def resolve_command(command: list[str]) -> list[str]:
    if not command:
        raise ValueError("Command cannot be empty.")

    executable = command[0]
    resolved = shutil.which(executable)
    if resolved is None and os.name == "nt":
        resolved = resolve_windows_command(executable)

    if resolved and resolved.lower().endswith(".ps1"):
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            resolved,
            *command[1:],
        ]

    if resolved:
        return [resolved, *command[1:]]

    return command


def resolve_windows_command(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Command {executable} -ErrorAction SilentlyContinue).Source",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except OSError:
        return None

    source = result.stdout.strip()
    return source or None


async def ask_manual_reply(prompt: dict[str, Any], logger: Logger) -> str | None:
    logger.write("")
    logger.write(f"Prompt [{prompt['id']}]: {prompt['text']}")
    reply = await asyncio.to_thread(input, "Reply to send, or blank to skip: ")
    reply = reply.strip()
    return reply or None


async def ask_ai_reply(
    config: WatcherConfig,
    prompt: dict[str, Any],
    logger: Logger,
    auto_send_ai: bool,
    page: Page,
    seen: set[str],
    sent_replies: list[str],
) -> str | None:
    logger.write("Generating Codex reply...", "yellow")
    personality = load_personality(config.personality_file)
    logger.write(
        f"Using persona file: {config.personality_file} ({len(personality)} chars)"
    )
    logger.write(f"Conversation partner: {prompt.get('username') or 'unknown'}", "cyan")
    logger.write(f"Saved Codex prompt debug file: {config.last_codex_prompt_file}")
    reply = await asyncio.to_thread(run_codex_reply, config, prompt)

    extra_context = await collect_new_context(
        page, config, seen, sent_replies, logger, active_prompt=prompt
    )
    if extra_context:
        logger.write("Regenerating Codex reply with newer chat activity.")
        prompt = {
            **prompt,
            "new_context": extra_context,
        }
        reply = await asyncio.to_thread(run_codex_reply, config, prompt)

    reply = normalize_message(reply)
    if not reply:
        logger.write("Codex returned an empty reply.")
        return None

    if is_invalid_reply_for_prompt(reply, prompt):
        logger.write(f"Rejected weak or off-topic Codex reply: {reply}", "red")
        fallback = fallback_reply_body(prompt)
        if fallback:
            logger.write(f"Using scripted fallback reply: {fallback}", "yellow")
            return fallback

        if auto_send_ai:
            logger.write(
                "Auto-send is enabled, so rejected Codex reply was skipped.",
                "red",
            )
            return None

        replacement = await asyncio.to_thread(
            input, "Type replacement reply, or blank to skip: "
        )
        replacement = replacement.strip()
        return replacement or None

    logger.write(f"Codex suggested: {reply}", "yellow")
    if auto_send_ai:
        return reply

    user_reply = await asyncio.to_thread(
        input, "Press Enter to send, type replacement, or type /skip: "
    )
    user_reply = user_reply.strip()
    if user_reply == "/skip":
        return None
    return user_reply or reply


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


async def collect_new_context(
    page: Page,
    config: WatcherConfig,
    seen: set[str],
    sent_replies: list[str],
    logger: Logger,
    active_prompt: dict[str, Any] | None = None,
    limit: int = 5,
) -> str:
    relevant_lines: list[str] = []
    logged_lines: list[str] = []
    messages = await extract_chat_messages(page, config.message_selectors)
    active_username = active_prompt.get("username") if active_prompt else None
    for message in messages:
        text = message.text
        if text in seen:
            continue
        seen.add(text)

        own_directed = parse_own_directed_message(text, config.nickname)
        if (
            config.ignore_own_timestamped_messages
            and looks_like_own_timestamped_message(text, config.nickname)
            and not own_directed
        ):
            logger.write(f"Ignored own timestamped message: {text}", "dim")
            continue

        if is_recent_sent_reply_echo(text, config.nickname, sent_replies):
            logger.write(f"Ignored recent sent reply echo: {text}", "dim")
            continue

        if own_directed:
            target, body = own_directed
            if target != active_username and not has_user_memory(config, target):
                logger.write(
                    f"Ignored first outbound message to untracked {target}: {body}",
                    "dim",
                )
                continue

        saved = append_chat_context(config, message)
        username = message.username or "unknown"
        line = f"{username}: {text}"
        if saved:
            logged_lines.append(line)

        if saved and (
            text.startswith(config.nickname)
            or own_directed
            or (active_username and message.username == active_username)
        ):
            relevant_lines.append(line)

    if logged_lines:
        logger.write("New chat activity saved while Codex was thinking:", "blue")
        for line in logged_lines[-limit:]:
            logger.write(f"  {line}", "blue")

    if logged_lines and not relevant_lines:
        logger.write("No new activity was relevant to the active tagged prompt.", "dim")

    return "\n".join(relevant_lines[-limit:])


def build_prompt_record(message: ChatMessage, source_url: str) -> dict[str, Any]:
    return {
        "id": prompt_id(message.text),
        "captured_at": utc_now(),
        "username": message.username,
        "text": message.text,
        "source_url": source_url,
        "status": "captured",
    }


def cdp_json_url(cdp_url: str) -> str:
    return cdp_url.rstrip("/") + "/json/version"


def is_cdp_ready(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(cdp_json_url(cdp_url), timeout=1) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


async def wait_for_cdp(cdp_url: str, timeout_seconds: float, logger: Logger) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if await asyncio.to_thread(is_cdp_ready, cdp_url):
            logger.write(f"Browser debugging endpoint is ready: {cdp_url}")
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for browser debugging endpoint: {cdp_url}")


def start_brave(config: WatcherConfig, logger: Logger) -> None:
    script = config.brave_script
    if not script.is_absolute():
        script = Path.cwd() / script

    if not script.exists():
        raise FileNotFoundError(f"Brave helper script not found: {script}")

    port_match = re.search(r":(\d+)", config.cdp_url)
    port = port_match.group(1) if port_match else "9222"
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Port",
        port,
    ]
    logger.write(f"Starting Brave with: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stdout.strip():
        logger.write(result.stdout.strip())
    if result.stderr.strip():
        logger.write(result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f"Brave startup script failed with code {result.returncode}.")


async def watch(
    config: WatcherConfig,
    send_replies: bool,
    manual_replies: bool,
    codex_replies: bool,
    auto_send_ai: bool,
    logger: Logger,
) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(config.cdp_url)
        page = await find_target_page(browser, config.target_url_contains)

        logger.write(f"Connected to: {page.url}")
        logger.write(f"Watching for messages starting with: {config.nickname}")
        logger.write(f"Reply inbox: {config.reply_inbox}")
        logger.write(f"Log file: {config.log_file}")
        if codex_replies:
            logger.write("Codex replies are ENABLED.")
            if auto_send_ai:
                logger.write("Codex replies will be sent automatically.")
            else:
                logger.write("Codex replies require terminal confirmation.")
        elif manual_replies:
            logger.write("Manual terminal replies are ENABLED.")
        elif send_replies:
            logger.write(
                "Reply sending is ENABLED. Non-empty reply inbox text will be sent."
            )
        else:
            logger.write("Reply sending is disabled. Use --send-replies to enable it.")
        logger.write("Press Ctrl+C to stop.")

        seen: set[str] = set()
        sent_replies: list[str] = []
        known_partners: set[str] = set()
        active_prompt: dict[str, Any] | None = None

        while True:
            page = await ensure_target_page(
                browser, page, config.target_url_contains, logger
            )
            messages = await extract_chat_messages(page, config.message_selectors)
            for message in messages:
                text = message.text
                if text in seen:
                    continue
                seen.add(text)

                own_directed = parse_own_directed_message(text, config.nickname)
                if (
                    config.ignore_own_timestamped_messages
                    and looks_like_own_timestamped_message(text, config.nickname)
                    and not own_directed
                ):
                    logger.write(f"Ignored own timestamped message: {text}", "dim")
                    continue

                if is_recent_sent_reply_echo(text, config.nickname, sent_replies):
                    logger.write(f"Ignored recent sent reply echo: {text}", "dim")
                    continue

                if own_directed:
                    target, body = own_directed
                    if target in known_partners or has_user_memory(config, target):
                        append_chat_context(config, message)
                        logger.write(f"Saved your message to {target}: {body}", "magenta")
                    else:
                        logger.write(
                            f"Ignored first outbound message to untracked {target}: {body}",
                            "dim",
                        )
                    continue

                saved_context = append_chat_context(config, message)

                if not saved_context:
                    continue

                if is_prompt_for_nickname(text, config.nickname):
                    if message.username:
                        known_partners.add(message.username)
                    active_prompt = build_prompt_record(message, page.url)
                    append_jsonl(config.output_jsonl, active_prompt)
                    append_jsonl(config.history_jsonl, active_prompt)
                    write_json(config.latest_prompt_json, active_prompt)
                    sender = f" from {message.username}" if message.username else ""
                    logger.write(
                        f"Captured prompt [{active_prompt['id']}]{sender}: {text}",
                        "cyan",
                    )

                    if manual_replies or codex_replies:
                        if codex_replies:
                            reply = await ask_ai_reply(
                                config,
                                active_prompt,
                                logger,
                                auto_send_ai,
                                page,
                                seen,
                                sent_replies,
                            )
                        else:
                            reply = await ask_manual_reply(active_prompt, logger)

                        if reply:
                            final_reply = address_reply(
                                reply, active_prompt.get("username")
                            )
                            reply_record = {
                                "id": active_prompt["id"],
                                "replied_at": utc_now(),
                                "prompt": active_prompt["text"],
                                "reply": final_reply,
                                "reply_body": reply,
                                "reply_partner": active_prompt.get("username"),
                                "source_url": page.url,
                                "status": "reply_sent",
                            }
                            page = await ensure_target_page(
                                browser, page, config.target_url_contains, logger
                            )
                            sent = await send_reply(page, config, final_reply, logger)
                            if sent:
                                sent_replies.append(final_reply)
                                sent_replies = sent_replies[
                                    -config.ignore_recent_sent_replies :
                                ]
                                if active_prompt.get("username"):
                                    known_partners.add(str(active_prompt["username"]))
                                    append_direct_context(
                                        config,
                                        str(active_prompt["username"]),
                                        config.nickname,
                                        final_reply,
                                    )
                            else:
                                reply_record["status"] = "reply_send_failed"
                            append_jsonl(config.history_jsonl, reply_record)
                            if sent:
                                logger.write(
                                    f"Sent reply for [{active_prompt['id']}]: {final_reply}",
                                    "green",
                                )
                        else:
                            append_jsonl(
                                config.history_jsonl,
                                {
                                    "id": active_prompt["id"],
                                    "skipped_at": utc_now(),
                                    "prompt": active_prompt["text"],
                                    "source_url": page.url,
                                    "status": "reply_skipped",
                                },
                            )
                            logger.write(f"Skipped reply for [{active_prompt['id']}].")
                        active_prompt = None

            if manual_replies or codex_replies:
                await asyncio.sleep(config.poll_interval_seconds)
                continue

            reply = read_reply(config.reply_inbox)
            if reply and active_prompt:
                final_reply = address_reply(reply, active_prompt.get("username"))
                reply_record = {
                    "id": active_prompt["id"],
                    "replied_at": utc_now(),
                    "prompt": active_prompt["text"],
                    "reply": final_reply,
                    "reply_body": reply,
                    "reply_partner": active_prompt.get("username"),
                    "source_url": page.url,
                    "status": "reply_ready",
                }

                if send_replies:
                    page = await ensure_target_page(
                        browser, page, config.target_url_contains, logger
                    )
                    sent = await send_reply(page, config, final_reply, logger)
                    if sent:
                        sent_replies.append(final_reply)
                        sent_replies = sent_replies[-config.ignore_recent_sent_replies :]
                        if active_prompt.get("username"):
                            known_partners.add(str(active_prompt["username"]))
                            append_direct_context(
                                config,
                                str(active_prompt["username"]),
                                config.nickname,
                                final_reply,
                            )
                        reply_record["status"] = "reply_sent"
                        logger.write(
                            f"Sent reply for [{active_prompt['id']}]: {final_reply}",
                            "green",
                        )
                    else:
                        reply_record["status"] = "reply_send_failed"
                else:
                    logger.write(f"Reply ready for [{active_prompt['id']}]: {reply}")

                append_jsonl(config.history_jsonl, reply_record)
                clear_reply(config.reply_inbox)
                active_prompt = None

            await asyncio.sleep(config.poll_interval_seconds)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch a manually opened Brave/Chromium chat page for tagged messages."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config JSON. Defaults to config.json.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Start Brave, then watch tags and generate Codex replies.",
    )
    run_parser.add_argument(
        "--wait-seconds",
        type=float,
        default=30,
        help="How long to wait for Brave remote debugging to become available.",
    )
    run_parser.add_argument(
        "--codex-replies",
        action="store_true",
        default=True,
        help="Generate replies with codex exec. This is the default for run.",
    )
    run_parser.add_argument(
        "--manual-replies",
        action="store_true",
        help="Type replies manually instead of using Codex.",
    )
    run_parser.add_argument(
        "--auto-send-ai",
        action="store_true",
        help="Send Codex replies without terminal confirmation, overriding config.",
    )
    run_parser.add_argument(
        "--confirm-replies",
        action="store_true",
        help="Require terminal confirmation before sending, overriding config.",
    )

    watch_parser = subparsers.add_parser(
        "watch", help="Watch chat messages and capture matching prompts."
    )
    watch_parser.add_argument(
        "--send-replies",
        action="store_true",
        help="Send text from reply_inbox back to the chat page.",
    )
    watch_parser.add_argument(
        "--manual-replies",
        action="store_true",
        help="Ask for a reply in the terminal whenever a prompt is captured.",
    )
    watch_parser.add_argument(
        "--codex-replies",
        action="store_true",
        help="Generate replies with codex exec whenever a prompt is captured.",
    )
    watch_parser.add_argument(
        "--auto-send-ai",
        action="store_true",
        help="Send Codex replies without terminal confirmation, overriding config.",
    )
    watch_parser.add_argument(
        "--confirm-replies",
        action="store_true",
        help="Require terminal confirmation before sending, overriding config.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect", help="Print selector matches to help tune config."
    )
    inspect_parser.add_argument("--limit", type=int, default=5)

    send_parser = subparsers.add_parser(
        "send", help="Send one message to the chat input using configured selectors."
    )
    send_parser.add_argument("text")

    return parser.parse_args()


def should_auto_send(config: WatcherConfig, args: argparse.Namespace) -> bool:
    if getattr(args, "auto_send_ai", False):
        return True
    if getattr(args, "confirm_replies", False):
        return False
    return not config.confirm_codex_replies


def main() -> None:
    args = parse_args()
    config = WatcherConfig.from_file(args.config)

    if args.command == "watch":
        logger = Logger(config.log_file)
        auto_send_ai = should_auto_send(config, args)
        asyncio.run(
            watch(
                config,
                args.send_replies,
                args.manual_replies,
                args.codex_replies,
                auto_send_ai,
                logger,
            )
        )
    elif args.command == "inspect":
        asyncio.run(inspect(config, args.limit))
    elif args.command == "send":
        asyncio.run(send_once(config, args.text))
    elif args.command == "run":
        codex_replies = args.codex_replies and not args.manual_replies
        auto_send_ai = should_auto_send(config, args)
        asyncio.run(
            run_all(
                config,
                args.wait_seconds,
                codex_replies,
                args.manual_replies,
                auto_send_ai,
            )
        )


if __name__ == "__main__":
    main()
