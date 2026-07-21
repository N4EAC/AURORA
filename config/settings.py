"""Central application settings for Aurora."""

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Values controlling the Aurora desktop application."""

    window_title: str = "Aurora"
    window_geometry: str = "900x600"
    minimum_width: int = 640
    minimum_height: int = 420
    background: str = "#15191f"
    foreground: str = "#e8edf2"
    muted_foreground: str = "#9ca8b5"
    log_level: str = "INFO"
    log_directory: Path = PROJECT_ROOT / "logs"
    log_filename: str = "aurora.log"
    log_max_bytes: int = 1_000_000
    log_backup_count: int = 3
    audio_sample_rate: int = 12_000
    audio_channels: int = 1
    audio_block_size: int = 1_024
    cat_port: str | None = None
    cat_baud_rate: int = 9_600
    cat_timeout_seconds: float = 0.5
    ptt_method: str = "cat"
    spectrum_fft_size: int = 1_024
    spectrum_floor_db: float = -120.0
    spectrum_ceiling_db: float = 0.0
    waterfall_history_size: int = 128
    contact_database: Path = PROJECT_ROOT / "data" / "aurora_contacts.sqlite3"


SETTINGS = AppSettings()
