from __future__ import annotations

import re
from pathlib import Path

from freddy_bot.config import WatcherConfig
from freddy_bot.utils import utc_now


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned[:80] or "unknown"

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
