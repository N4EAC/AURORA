"""Persistent amateur-radio contact records for Aurora."""

from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


@dataclass(frozen=True, slots=True, init=False)
class ContactRecord:
    """One logged Aurora contact."""

    callsign: str
    frequency_hz: int
    mode: str
    sent_report: str
    received_report: str
    message: str
    notes: str
    logged_at: datetime
    database_id: int | None

    def __init__(
        self,
        callsign: str,
        frequency_hz: int,
        mode: str = "Aurora",
        sent_report: str = "",
        received_report: str = "",
        message: str = "",
        notes: str = "",
        logged_at: datetime | None = None,
        database_id: int | None = None,
    ) -> None:
        object.__setattr__(self, "callsign", callsign.strip().upper())
        object.__setattr__(self, "frequency_hz", frequency_hz)
        object.__setattr__(self, "mode", mode.strip())
        object.__setattr__(self, "sent_report", sent_report.strip())
        object.__setattr__(self, "received_report", received_report.strip())
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "notes", notes)
        object.__setattr__(self, "logged_at", logged_at or datetime.now(timezone.utc))
        object.__setattr__(self, "database_id", database_id)
        if not self.callsign:
            raise ValueError("A callsign is required")
        if self.frequency_hz <= 0:
            raise ValueError("Contact frequency must be positive")


class ContactLog:
    """SQLite-backed storage for Aurora contact records."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        logged_at TEXT NOT NULL,
                        callsign TEXT NOT NULL,
                        frequency_hz INTEGER NOT NULL,
                        mode TEXT NOT NULL,
                        sent_report TEXT NOT NULL,
                        received_report TEXT NOT NULL,
                        message TEXT NOT NULL,
                        notes TEXT NOT NULL
                    )
                    """
                )

    def add(self, contact: ContactRecord) -> ContactRecord:
        """Persist a contact and return it with its database identifier."""
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO contacts (
                        logged_at, callsign, frequency_hz, mode,
                        sent_report, received_report, message, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contact.logged_at.isoformat(),
                        contact.callsign,
                        contact.frequency_hz,
                        contact.mode,
                        contact.sent_report,
                        contact.received_report,
                        contact.message,
                        contact.notes,
                    ),
                )
        return replace(contact, database_id=int(cursor.lastrowid))

    def recent(self, limit: int = 100) -> tuple[ContactRecord, ...]:
        """Return the most recently logged contacts, newest first."""
        if limit <= 0:
            raise ValueError("Contact query limit must be positive")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM contacts ORDER BY logged_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ContactRecord:
        return ContactRecord(
            callsign=row["callsign"],
            frequency_hz=row["frequency_hz"],
            mode=row["mode"],
            sent_report=row["sent_report"],
            received_report=row["received_report"],
            message=row["message"],
            notes=row["notes"],
            logged_at=datetime.fromisoformat(row["logged_at"]),
            database_id=row["id"],
        )
