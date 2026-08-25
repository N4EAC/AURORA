"""Operator-selected canned-message expansion for native Aurora chat."""

from __future__ import annotations

from datetime import datetime, timezone


CANNED_MESSAGES = {
    "Custom": "",
    "CQ": "CQ CQ from <CALL> <NAME>",
    "Calling": "<CALL> calling",
    "Station ID": "This is <NAME>, <CALL>",
    "Time": "Current UTC time <TIME>",
}


def expand_message_template(
    template: str,
    *,
    name: str,
    callsign: str,
    now: datetime | None = None,
) -> str:
    """Expand supported station tokens immediately before transmission."""
    timestamp = now or datetime.now(timezone.utc)
    values = {
        "<NAME>": name.strip(),
        "<CALL>": callsign.strip().upper(),
        "<TIME>": timestamp.astimezone(timezone.utc).strftime("%H:%M UTC"),
    }
    expanded = template
    for token, value in values.items():
        expanded = expanded.replace(token, value)
    return expanded.strip()
