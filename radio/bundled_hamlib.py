"""Lifecycle management for Aurora's private Hamlib rigctld service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import socket
import subprocess
import time

from tools.bootstrap_hamlib import rigctld_path


@dataclass(frozen=True, slots=True)
class BundledHamlibConfig:
    """Operator-selected arguments for one private rigctld process."""

    model: int
    device: str
    baud_rate: int = 9_600
    port: int = 4_532

    def __post_init__(self) -> None:
        if self.model <= 0:
            raise ValueError("Hamlib radio model number must be positive")
        if not self.device.strip():
            raise ValueError("Radio CAT device is required")
        if self.baud_rate <= 0:
            raise ValueError("Radio CAT baud rate must be positive")
        if not 1 <= self.port <= 65_535:
            raise ValueError("Private rigctld port must be between 1 and 65535")


class BundledHamlibService:
    """Start and stop the rigctld executable shipped with Aurora."""

    def __init__(self, executable: Path | None = None) -> None:
        self.executable = executable or rigctld_path()
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def running(self) -> bool:
        """Return whether the private rigctld process remains active."""
        return self._process is not None and self._process.poll() is None

    def start(self, config: BundledHamlibConfig, timeout: float = 5.0) -> None:
        """Launch private rigctld and wait until its localhost port is ready."""
        if self.running:
            raise RuntimeError("Aurora's bundled Hamlib service is already running")
        if not self.executable.is_file():
            raise FileNotFoundError(
                "Aurora bundled Hamlib runtime is missing; run its bootstrap tool"
            )
        self._process = subprocess.Popen(
            [
                str(self.executable),
                "-m",
                str(config.model),
                "-r",
                config.device,
                "-s",
                str(config.baud_rate),
                "-T",
                "127.0.0.1",
                "-t",
                str(config.port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                error = self._process.stderr.read().decode("utf-8", errors="replace")
                self._process = None
                raise RuntimeError(f"Bundled Hamlib failed to start: {error.strip()}")
            try:
                with socket.create_connection(("127.0.0.1", config.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.05)
        self.stop()
        raise TimeoutError("Bundled Hamlib did not become ready")

    def stop(self) -> None:
        """Stop Aurora's private rigctld process."""
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)
