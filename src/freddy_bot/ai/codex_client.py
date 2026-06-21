from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from freddy_bot.ai.prompt_builder import build_codex_prompt
from freddy_bot.config import WatcherConfig


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
