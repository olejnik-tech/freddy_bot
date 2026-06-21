from __future__ import annotations

import re

from freddy_bot.chat.parsing import normalize_message


def address_reply(reply: str, partner: str | None) -> str:
    reply = normalize_message(reply)
    if not partner:
        return reply

    reply = re.sub(
        rf"^(hey|hi|hello)\s+{re.escape(partner)}\b[,\s:-]*",
        r"\1 ",
        reply,
        flags=re.IGNORECASE,
    )
    reply = normalize_message(reply)

    if reply.lower().startswith(partner.lower()):
        reply = reply[len(partner) :].lstrip(" ,:-")

    return f"{partner} {reply}"
