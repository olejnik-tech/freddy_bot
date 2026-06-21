from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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
    bot_prevention_enabled: bool
    bot_prevention_min_message_chars: int
    bot_prevention_repeated_count: int
    bot_prevention_guest_rank_only: bool
    bot_prevention_immediate_score: int
    bot_prevention_repeat_score: int
    user_menu_selectors: tuple[str, ...]
    user_action_selectors: tuple[str, ...]
    user_ignore_selectors: tuple[str, ...]

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
            bot_prevention_enabled=bool(data.get("bot_prevention_enabled", True)),
            bot_prevention_min_message_chars=int(
                data.get("bot_prevention_min_message_chars", 240)
            ),
            bot_prevention_repeated_count=int(
                data.get("bot_prevention_repeated_count", 2)
            ),
            bot_prevention_guest_rank_only=bool(
                data.get("bot_prevention_guest_rank_only", True)
            ),
            bot_prevention_immediate_score=int(
                data.get("bot_prevention_immediate_score", 8)
            ),
            bot_prevention_repeat_score=int(
                data.get("bot_prevention_repeat_score", 4)
            ),
            user_menu_selectors=tuple(
                data.get(
                    "user_menu_selectors",
                    [
                        "div.avtrig.chat_avatar",
                        "div.avs_menu.chat_avatar",
                        "img.cavatar",
                        "img.avav",
                        "div[class*='avtrig'][class*='chat_avatar']",
                        "img[class*='cavatar']",
                        "img[class*='avav']",
                        ".avatar",
                        ".avtrig",
                        ".av",
                        ".my_avatar",
                        ".chat_avatar",
                        ".chat_head",
                        ".chat_image",
                        "img",
                        "[class*='avatar']",
                        "[class*='avtrig']",
                    ],
                )
            ),
            user_action_selectors=tuple(
                data.get(
                    "user_action_selectors",
                    [
                        ".get_actions.avactions",
                        ".avactions",
                        "text=/action/i",
                        "text=Action",
                        "text=Actions",
                        "text=More",
                        "text=/more/i",
                        "text=Menu",
                        "text=/menu/i",
                        "[class*='action']",
                    ],
                )
            ),
            user_ignore_selectors=tuple(
                data.get(
                    "user_ignore_selectors",
                    [
                        "#ignore_private",
                        "[name='acu_ignore']",
                        "[data-boom='action/action_member'][name='acu_ignore']",
                        "#glob_actions > div:nth-child(3) > div.sub_list_content",
                        "xpath=//*[@id='glob_actions']/div[3]/div[2]",
                        "text=/ignore/i",
                        "text=/block/i",
                        "text=Ignore",
                        "text=Ignore user",
                        "text=Block",
                        "text=Block user",
                        "[onclick*='ignore']",
                        "[onclick*='Ignore']",
                        "[data-action*='ignore']",
                        "[data-command*='ignore']",
                        "[class*='ignore']",
                        "[class*='block']",
                    ],
                )
            ),
        )
