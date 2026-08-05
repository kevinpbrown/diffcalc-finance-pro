"""Splash screen — Flow F-1.

The splash is purely presentational. The App's startup worker drives
initialisation and updates the status label directly before transitioning away.
Pressing Enter at any point signals the startup worker to skip the minimum
display timer.
"""

from __future__ import annotations

import asyncio

from rich.text import Text as RichText
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Static

from personal_finance import __version__
from personal_finance.ui.palette import BORDER_STRUCTURAL, TEXT_HINT

# Block-letter "DiffCalc" / "Finance Pro" wordmark (FIGlet "ansi_shadow" font),
# with a hand-added 1-cell drop shadow: each solid glyph cell casts a "▓" one
# row/column down-right, wherever that cell would otherwise be blank. Rendered
# as two-tone Rich text by _build_logo() below — see gotcha #6 in
# ui/README.md for why this can't just be a plain markup string.
_SHADOW_CHAR = "▓"

_LOGO = """\
██████╗ ██╗███████╗███████╗ ██████╗ █████╗ ██╗      ██████╗
██╔══██╗██║██╔════╝██╔════╝██╔════╝██╔══██╗██║▓    ██╔════╝▓
██║▓▓██║██║█████╗▓▓█████╗▓▓██║▓▓▓▓▓███████║██║▓    ██║▓▓▓▓▓▓
██║▓ ██║██║██╔══╝▓ ██╔══╝▓ ██║▓    ██╔══██║██║▓    ██║▓
██████╔╝██║██║▓▓▓▓ ██║▓▓▓▓ ╚██████╗██║▓▓██║███████╗╚██████╗
╚═════╝▓╚═╝╚═╝▓    ╚═╝▓     ╚═════╝╚═╝▓ ╚═╝╚══════╝▓╚═════╝▓
 ▓▓▓▓▓▓▓ ▓▓▓▓▓▓     ▓▓▓      ▓▓▓▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓

███████╗██╗███╗   ██╗ █████╗ ███╗   ██╗ ██████╗███████╗    ██████╗ ██████╗  ██████╗
██╔════╝██║████╗  ██║██╔══██╗████╗  ██║██╔════╝██╔════╝▓   ██╔══██╗██╔══██╗██╔═══██╗
█████╗▓▓██║██╔██╗ ██║███████║██╔██╗ ██║██║▓▓▓▓▓█████╗▓▓▓   ██████╔╝██████╔╝██║▓▓▓██║▓
██╔══╝▓ ██║██║╚██╗██║██╔══██║██║╚██╗██║██║▓    ██╔══╝▓     ██╔═══╝▓██╔══██╗██║▓  ██║▓
██║▓▓▓▓ ██║██║▓╚████║██║▓▓██║██║▓╚████║╚██████╗███████╗    ██║▓▓▓▓▓██║▓▓██║╚██████╔╝▓
╚═╝▓    ╚═╝╚═╝▓ ╚═══╝╚═╝▓ ╚═╝╚═╝▓ ╚═══╝▓╚═════╝╚══════╝▓   ╚═╝▓    ╚═╝▓ ╚═╝▓╚═════╝▓▓
 ▓▓▓     ▓▓▓▓▓▓  ▓▓▓▓▓▓▓▓  ▓▓▓▓▓▓  ▓▓▓▓▓ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    ▓▓▓     ▓▓▓  ▓▓▓ ▓▓▓▓▓▓▓"""


def _build_logo() -> RichText:
    """Render :data:`_LOGO` as two-tone Rich text.

    Glyph cells render bold white; ``_SHADOW_CHAR`` cells render in the
    structural-border blue so the drop shadow reads as secondary to the
    letterforms rather than equal weight.

    Returns:
        A :class:`~rich.text.Text` ready to pass straight to ``Static``.
    """
    text = RichText()
    lines = _LOGO.split("\n")
    for i, line in enumerate(lines):
        for char in line:
            if char == _SHADOW_CHAR:
                text.append(char, style=BORDER_STRUCTURAL)
            elif char != " ":
                text.append(char, style="bold #ffffff")
            else:
                text.append(" ")
        if i < len(lines) - 1:
            text.append("\n")
    return text


class SplashScreen(Screen[None]):
    """Splash screen shown at application startup (Flow F-1).

    The App's ``_startup_worker`` updates ``#splash-status`` to reflect
    progress, then calls ``app.switch_screen(DashboardScreen())``.
    Pressing Enter at any time signals the startup worker to skip the minimum
    display timer.
    """

    DEFAULT_CSS = f"""
    SplashScreen {{
        align: center middle;
    }}

    #splash-inner {{
        width: auto;
        height: auto;
    }}

    #splash-logo {{
        color: #ffffff;
        width: auto;
        margin-bottom: 1;
    }}

    #splash-version {{
        color: #aaaaff;
        text-align: center;
        width: auto;
    }}

    #splash-copyright {{
        color: #aaaaaa;
        text-align: center;
        width: auto;
        margin-top: 1;
    }}

    #splash-status {{
        color: #aaaaaa;
        text-align: center;
        width: auto;
        margin-top: 1;
    }}

    #splash-skip-hint {{
        color: {TEXT_HINT};
        text-align: center;
        width: auto;
        margin-top: 1;
    }}
    """

    def __init__(self) -> None:
        """Initialize with a skip event for signalling the startup worker."""
        super().__init__()
        self._skip_event: asyncio.Event = asyncio.Event()

    def compose(self) -> ComposeResult:
        """Render the splash layout."""
        with Vertical(id="splash-inner"):
            yield Static(_build_logo(), id="splash-logo")
            yield Static(f"v{__version__}", id="splash-version")
            yield Static("Copyright (c) 2026 Kevin Brown", id="splash-copyright")
            yield Static("Starting…", id="splash-status")
            yield Static("Press Enter to skip", id="splash-skip-hint")
        yield Footer()

    def on_key(self, event: Key) -> None:
        """Signal the startup worker to skip the minimum display timer."""
        if event.key == "enter":
            self._skip_event.set()
            event.stop()

    def set_status(self, text: str) -> None:
        """Update the status line shown below the version string.

        Args:
            text: Short human-readable progress description.
        """
        try:
            self.query_one("#splash-status", Static).update(text)
        except Exception:  # noqa: BLE001
            pass  # Worker can fire before compose() in headless/test mode — best-effort
