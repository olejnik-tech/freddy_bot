from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WatchMode:
    send_replies: bool
    manual_replies: bool
    codex_replies: bool
    auto_send_ai: bool


@dataclass
class WatchState:
    seen: set[str] = field(default_factory=set)
    sent_replies: list[str] = field(default_factory=list)
    known_partners: set[str] = field(default_factory=set)
    bot_prevention_seen_dom_ids: set[str] = field(default_factory=set)
    long_message_repeats: dict[str, int] = field(default_factory=dict)
    ignored_users: set[str] = field(default_factory=set)
    failed_ignore_attempts: dict[str, datetime] = field(default_factory=dict)
    active_prompt: dict[str, Any] | None = None
