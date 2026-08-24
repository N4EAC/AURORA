"""Cross-platform visual system for the Aurora desktop interface."""

from __future__ import annotations

from dataclasses import dataclass
import platform
import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True, slots=True)
class AuroraPalette:
    """Colors shared by Aurora's Tkinter widgets and canvas views."""

    background: str = "#0b1016"
    surface: str = "#121a23"
    surface_raised: str = "#18232e"
    border: str = "#293846"
    foreground: str = "#eef5f7"
    muted: str = "#8fa2b3"
    accent: str = "#47dbc6"
    accent_active: str = "#65ead7"
    blue: str = "#68a7ff"
    warning: str = "#f5bd4f"
    danger: str = "#ff7070"
    field: str = "#0d141c"


PALETTE = AuroraPalette()


def font_families(system: str | None = None) -> tuple[str, str]:
    """Return UI and monospace font families appropriate for the platform."""
    current = system or platform.system()
    if current == "Darwin":
        return "SF Pro Text", "SF Mono"
    if current == "Windows":
        return "Segoe UI", "Cascadia Mono"
    return "DejaVu Sans", "DejaVu Sans Mono"


def configure_theme(root: tk.Tk) -> AuroraPalette:
    """Apply Aurora's portable ttk theme and return its color palette."""
    ui_font, mono_font = font_families()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.option_add("*Font", (ui_font, 10))
    root.option_add("*TCombobox*Listbox.font", (ui_font, 10))

    style.configure(".", background=PALETTE.background, foreground=PALETTE.foreground)
    style.configure("Aurora.TFrame", background=PALETTE.background)
    style.configure("Aurora.Surface.TFrame", background=PALETTE.surface)
    style.configure("Aurora.Panel.TFrame", background=PALETTE.surface)
    style.configure("Aurora.Raised.TFrame", background=PALETTE.surface_raised)
    style.configure(
        "Aurora.Title.TLabel",
        background=PALETTE.background,
        foreground=PALETTE.foreground,
        font=(ui_font, 24, "bold"),
    )
    style.configure(
        "Aurora.Subtitle.TLabel",
        background=PALETTE.background,
        foreground=PALETTE.muted,
        font=(ui_font, 10),
    )
    style.configure(
        "Aurora.Section.TLabel",
        background=PALETTE.surface,
        foreground=PALETTE.foreground,
        font=(ui_font, 10, "bold"),
    )
    style.configure(
        "Aurora.Muted.TLabel",
        background=PALETTE.surface,
        foreground=PALETTE.muted,
        font=(ui_font, 9),
    )
    style.configure(
        "Aurora.Status.TLabel",
        background=PALETTE.background,
        foreground=PALETTE.muted,
        font=(ui_font, 9, "bold"),
    )
    style.configure(
        "Aurora.Value.TLabel",
        background=PALETTE.surface,
        foreground=PALETTE.accent,
        font=(mono_font, 9, "bold"),
    )
    style.configure(
        "Aurora.Warning.TLabel",
        background=PALETTE.surface_raised,
        foreground=PALETTE.warning,
        padding=(12, 7),
        font=(ui_font, 9, "bold"),
    )
    style.configure(
        "Aurora.CardTitle.TLabel",
        background=PALETTE.surface,
        foreground=PALETTE.muted,
        font=(ui_font, 9, "bold"),
    )
    style.configure(
        "Aurora.Primary.TButton",
        background=PALETTE.accent,
        foreground="#07110f",
        bordercolor=PALETTE.accent,
        padding=(14, 8),
        font=(ui_font, 9, "bold"),
    )
    style.map(
        "Aurora.Primary.TButton",
        background=[("active", PALETTE.accent_active), ("disabled", PALETTE.border)],
        foreground=[("disabled", PALETTE.muted)],
    )
    style.configure(
        "TButton",
        background=PALETTE.surface_raised,
        foreground=PALETTE.foreground,
        bordercolor=PALETTE.border,
        padding=(10, 7),
    )
    style.map("TButton", background=[("active", PALETTE.border)])
    style.configure(
        "TEntry",
        fieldbackground=PALETTE.field,
        foreground=PALETTE.foreground,
        insertcolor=PALETTE.foreground,
        bordercolor=PALETTE.border,
        padding=7,
    )
    style.configure(
        "TCombobox",
        fieldbackground=PALETTE.field,
        foreground=PALETTE.foreground,
        arrowcolor=PALETTE.muted,
        bordercolor=PALETTE.border,
        padding=5,
    )
    style.configure(
        "TSpinbox",
        fieldbackground=PALETTE.field,
        foreground=PALETTE.foreground,
        arrowcolor=PALETTE.muted,
        bordercolor=PALETTE.border,
        padding=4,
    )
    style.configure("TNotebook", background=PALETTE.background, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=PALETTE.surface,
        foreground=PALETTE.muted,
        padding=(14, 8),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", PALETTE.surface_raised)],
        foreground=[("selected", PALETTE.foreground)],
    )
    style.configure(
        "Treeview",
        background=PALETTE.field,
        fieldbackground=PALETTE.field,
        foreground=PALETTE.foreground,
        rowheight=26,
        bordercolor=PALETTE.border,
    )
    style.configure(
        "Treeview.Heading",
        background=PALETTE.surface_raised,
        foreground=PALETTE.muted,
        font=(ui_font, 9, "bold"),
    )
    return PALETTE
