from __future__ import annotations

from pathlib import Path

from freddy_bot.utils import utc_now


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
