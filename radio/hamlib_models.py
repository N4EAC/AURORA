"""Discover operator-readable radio models from Aurora's Hamlib runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from tools.bootstrap_hamlib import rigctld_path
from radio.subprocess_support import hidden_process_kwargs


@dataclass(frozen=True, slots=True)
class HamlibRadioModel:
    """One Hamlib backend presented by manufacturer and radio model."""

    model_id: int
    manufacturer: str
    model: str

    @property
    def display_name(self) -> str:
        """Return the operator-facing selection label."""
        return f"{self.manufacturer} {self.model}".strip()


FALLBACK_MODELS = (
    HamlibRadioModel(1, "Hamlib", "Dummy"),
    HamlibRadioModel(2, "Hamlib", "NET rigctl"),
    HamlibRadioModel(3073, "Icom", "IC-7300"),
)


def parse_model_list(output: str) -> tuple[HamlibRadioModel, ...]:
    """Parse the fixed-column table emitted by ``rigctld -l``."""
    models: list[HamlibRadioModel] = []
    for line in output.splitlines():
        fields = line.split()
        if not fields or not fields[0].isdigit() or len(fields) < 3:
            continue
        model_id = int(fields[0])
        revision_index = next(
            (index for index, value in enumerate(fields[2:], 2) if value[0:1].isdigit()),
            len(fields),
        )
        model_words = fields[2:revision_index]
        if not model_words:
            continue
        models.append(HamlibRadioModel(model_id, fields[1], " ".join(model_words)))
    unique = {item.model_id: item for item in models}
    return tuple(sorted(unique.values(), key=lambda item: item.display_name.casefold()))


def list_radio_models(executable: Path | None = None) -> tuple[HamlibRadioModel, ...]:
    """Return models reported by Hamlib, or a small usable fallback list."""
    program = executable or rigctld_path()
    if not program.is_file():
        return FALLBACK_MODELS
    try:
        result = subprocess.run(
            [str(program), "-l"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return FALLBACK_MODELS
    return parse_model_list(result.stdout) or FALLBACK_MODELS
