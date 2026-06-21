from __future__ import annotations

import re


def normalize_message(text: str) -> str:
    text = text.replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

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
