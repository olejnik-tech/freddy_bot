from __future__ import annotations

import asyncio
import urllib.error
import urllib.request

from freddy_bot.logging import Logger


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
