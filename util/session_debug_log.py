"""Structured debug logging for Aurora operator test sessions."""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any


class SessionDebugLog:
    """Write flushed, line-oriented events to one timestamped session file."""

    def __init__(self, directory: str | Path, application_version: str) -> None:
        log_directory = Path(directory)
        log_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        self.path = log_directory / f"aurora_test_session_{timestamp}.log"
        self._lock = threading.Lock()
        self._closed = False
        self._file = self.path.open("w", encoding="utf-8", buffering=1)
        self.record(
            "SESSION_START",
            application="Aurora",
            version=application_version,
            mode="simulation_only",
        )

    def record(self, event: str, **fields: Any) -> None:
        """Append and flush one structured session event."""
        normalized_event = event.strip().upper()
        if not normalized_event:
            raise ValueError("Session event name is required")
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        values = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=True, separators=(',', ':'))}"
            for key, value in sorted(fields.items())
        )
        line = f"{timestamp} | {normalized_event}"
        if values:
            line += f" | {values}"
        with self._lock:
            if self._closed:
                return
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        """Record normal session completion and close the file."""
        with self._lock:
            if self._closed:
                return
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            self._file.write(f"{timestamp} | SESSION_END | reason=\"normal_close\"\n")
            self._file.flush()
            self._file.close()
            self._closed = True

    def __enter__(self) -> "SessionDebugLog":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
