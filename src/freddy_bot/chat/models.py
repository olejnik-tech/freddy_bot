from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    text: str
    username: str | None = None
    user_id: str | None = None
    user_rank: int | None = None
    dom_id: str | None = None
    element: Any | None = None
