"""Operator-selected canned-message expansion for native Aurora chat."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass


CANNED_MESSAGES = {
    "Custom": "",
    "CQ": "CQ CQ from <CALL> <NAME>",
    "Calling": "<CALL> calling",
    "Station ID": "This is <NAME>, <CALL>",
    "Time": "Current UTC time <TIME>",
}


@dataclass(frozen=True, slots=True)
class PreparedMessage:
    """Expanded chat text and one-shot conversational control directives."""

    text: str
    back_to_you: bool = False
    end_of_call: bool = False


def expand_message_template(
    template: str,
    *,
    name: str,
    callsign: str,
    target_callsign: str = "",
    target_name: str = "",
    now: datetime | None = None,
) -> str:
    """Expand supported station tokens immediately before transmission."""
    timestamp = now or datetime.now(timezone.utc)
    values = {
        "<NAME>": name.strip(),
        "<CALL>": callsign.strip().upper(),
        "<TCALL>": target_callsign.strip().upper(),
        "<TNAME>": target_name.strip() or target_callsign.strip().upper(),
        "<TIME>": timestamp.astimezone(timezone.utc).strftime("%H:%M UTC"),
    }
    expanded = template
    for token, value in values.items():
        expanded = expanded.replace(token, value)
    return expanded.strip()


def prepare_message_template(
    template: str,
    *,
    name: str,
    callsign: str,
    target_callsign: str = "",
    target_name: str = "",
    now: datetime | None = None,
) -> PreparedMessage:
    """Resolve text tokens and convert BTY/EOC directives into control flags."""
    back_to_you = "<BTY>" in template
    end_of_call = "<EOC>" in template
    if back_to_you and end_of_call:
        raise ValueError("BTY and EOC cannot be sent together")
    if ("<TCALL>" in template or "<TNAME>" in template) and not target_callsign.strip():
        raise ValueError("Select a target station before using target tokens")
    text_template = template.replace("<BTY>", "").replace("<EOC>", "")
    text = expand_message_template(
        text_template,
        name=name,
        callsign=callsign,
        target_callsign=target_callsign,
        target_name=target_name,
        now=now,
    )
    return PreparedMessage(text, back_to_you, end_of_call)
