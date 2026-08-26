"""Connectionless Reply Channel state for one active Aurora conversation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import secrets
import time


MAX_REPLY_OFFSET_HZ = 10_000
DEFAULT_REPLY_WINDOW_SECONDS = 120


class TurnState(str, Enum):
    """Operator-facing conversational state without a negotiated connection."""

    ACTIVE = "ACTIVE"
    WAITING_FOR_REPLY = "WAITING FOR REPLY"
    PEER_PASSED_TURN = "YOUR TURN"


@dataclass(frozen=True, slots=True)
class ContactSession:
    """One locally accepted complementary RX/TX routing arrangement."""

    contact_id: int
    peer_callsign: str
    peer_name: str
    normal_frequency_hz: int
    normal_mode: str
    receive_frequency_hz: int
    transmit_frequency_hz: int
    expires_at: float
    turn_state: TurnState = TurnState.ACTIVE

    @property
    def split(self) -> bool:
        return self.receive_frequency_hz != self.transmit_frequency_hz

    def expired(self, now: float | None = None) -> bool:
        return (time.monotonic() if now is None else now) >= self.expires_at


def validate_reply_frequency(calling_hz: int, reply_hz: int) -> None:
    """Reject invalid or excessively separated Reply-To dial frequencies."""
    if calling_hz <= 0 or reply_hz <= 0:
        raise ValueError("Calling and Reply-To frequencies must be positive")
    if abs(reply_hz - calling_hz) > MAX_REPLY_OFFSET_HZ:
        raise ValueError("Reply-To frequency must be within ±10 kHz")


class ContactManager:
    """Own one optional contact route and make local return unconditional."""

    def __init__(self) -> None:
        self.active: ContactSession | None = None

    def offer(
        self,
        *,
        local_callsign: str,
        normal_frequency_hz: int,
        reply_frequency_hz: int,
        mode: str,
        window_seconds: int = DEFAULT_REPLY_WINDOW_SECONDS,
    ) -> ContactSession:
        """Create the caller route: transmit normally and listen on Reply-To."""
        del local_callsign
        validate_reply_frequency(normal_frequency_hz, reply_frequency_hz)
        self.active = ContactSession(
            secrets.randbits(32) or 1,
            "AURORA",
            "",
            normal_frequency_hz,
            mode,
            reply_frequency_hz,
            normal_frequency_hz,
            time.monotonic() + window_seconds,
        )
        return self.active

    def accept(
        self,
        *,
        peer_callsign: str,
        peer_name: str,
        contact_id: int,
        received_frequency_hz: int,
        reply_frequency_hz: int,
        normal_frequency_hz: int,
        mode: str,
        window_seconds: int,
    ) -> ContactSession:
        """Accept an offer while continuing to receive on its calling channel."""
        if contact_id == 0:
            raise ValueError("Reply offer has no contact ID")
        validate_reply_frequency(received_frequency_hz, reply_frequency_hz)
        self.active = ContactSession(
            contact_id,
            peer_callsign,
            peer_name.strip(),
            normal_frequency_hz,
            mode,
            received_frequency_hz,
            reply_frequency_hz,
            time.monotonic() + max(1, window_seconds),
        )
        return self.active

    def update_turn(self, state: TurnState) -> ContactSession | None:
        """Update BTY presentation without creating a protocol connection."""
        if self.active is None:
            return None
        current = self.active
        self.active = ContactSession(
            current.contact_id, current.peer_callsign, current.peer_name,
            current.normal_frequency_hz, current.normal_mode,
            current.receive_frequency_hz, current.transmit_frequency_hz,
            current.expires_at, state,
        )
        return self.active

    def bind_peer(self, callsign: str, name: str = "") -> ContactSession | None:
        """Bind the first directed responder to a broadcast reply offer."""
        if self.active is None or self.active.peer_callsign != "AURORA":
            return self.active
        current = self.active
        self.active = ContactSession(
            current.contact_id, callsign.strip().upper(), name.strip(),
            current.normal_frequency_hz, current.normal_mode,
            current.receive_frequency_hz, current.transmit_frequency_hz,
            current.expires_at, current.turn_state,
        )
        return self.active

    def refresh(self, window_seconds: int = DEFAULT_REPLY_WINDOW_SECONDS) -> None:
        """Extend an active route after matching contact activity."""
        if self.active is None:
            return
        current = self.active
        self.active = ContactSession(
            current.contact_id, current.peer_callsign, current.peer_name,
            current.normal_frequency_hz, current.normal_mode,
            current.receive_frequency_hz, current.transmit_frequency_hz,
            time.monotonic() + max(1, window_seconds), current.turn_state,
        )

    def return_to_normal(self) -> ContactSession | None:
        """Clear contact state locally without requiring EOC or any RF signal."""
        previous = self.active
        self.active = None
        return previous
