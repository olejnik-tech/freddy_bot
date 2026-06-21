from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def prompt_id(text: str) -> str:
    digest = hashlib.sha1(f"{utc_now()}:{text}".encode("utf-8")).hexdigest()
    return digest[:12]
