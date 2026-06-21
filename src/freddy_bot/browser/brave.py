from __future__ import annotations

import re
import subprocess
from pathlib import Path

from freddy_bot.config import WatcherConfig
from freddy_bot.logging import Logger


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
