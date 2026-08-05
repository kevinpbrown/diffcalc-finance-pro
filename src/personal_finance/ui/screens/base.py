"""Shared base classes for Textual screens and pane widgets."""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Click
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static

from personal_finance.ui.palette import BORDER_STRUCTURAL, PANEL_FILL
from personal_finance.ui.widgets.split_footer import SplitFooter


class LeftNavPane(Widget):
    """Shared base for focusable left-pane nav lists rendered as Rich Text.

    Owns the common CSS (padding, overflow, focus border), the ``on_select``
    callback, the current selection index, and mouse-click routing.

    Subclasses implement :meth:`_y_to_item_idx` to map a widget-relative
    y-coordinate (including top padding) to an item list index, or ``None``
    for non-item rows (header, separator, padding).

    ``on_click`` is already implemented here — do **not** override it.
    """

    can_focus = True

    DEFAULT_CSS = """
    LeftNavPane {
        width: 1fr;
        height: 1fr;
        padding: 1 1;
        overflow-y: auto;
    }
    LeftNavPane:focus {
        border-left: solid #aaaaff;
    }
    """

    def __init__(
        self,
        id: str | None = None,
        on_select: Callable[[int], None] | None = None,
    ) -> None:
        """Store the callback and initialise the selection index."""
        super().__init__(id=id)
        self._on_select = on_select
        self._selected_idx: int = 0

    def on_click(self, event: Click) -> None:
        """Route a mouse click to on_select, ignoring same-item clicks."""
        idx = self._y_to_item_idx(event.y)
        if idx is not None and idx != self._selected_idx and self._on_select is not None:
            self._on_select(idx)

    def _y_to_item_idx(self, y: int) -> int | None:
        """Map a widget-relative y coordinate to an item list index.

        Returns ``None`` for padding rows, header/separator lines, and
        out-of-range positions.  Subclasses must override this.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement _y_to_item_idx()")


class TwoPaneScreen(Screen[None]):
    """Base for screens with a 33/67 left-nav / right-content split layout.

    Provides the standard title bar, split body container, and ``SplitFooter``.
    Subclasses implement :meth:`_compose_left_pane` and :meth:`_compose_right_pane`
    to yield widgets into each side.

    CSS IDs owned by this base class:
      ``#tps-title-bar``  — top bar container
      ``#tps-title``      — left-aligned screen name label
      ``#tps-date``       — right-aligned effective date label
      ``#tps-body``       — the horizontal split container
      ``#tps-left``       — 33% left pane (widget yielded by subclass)
      ``#tps-right``      — 1fr right pane (widget/container yielded by subclass)
    """

    SCREEN_TITLE: ClassVar[str] = ""
    _CONTEXTUAL_ACTIONS: ClassVar[frozenset[str]] = frozenset()

    DEFAULT_CSS = f"""
    TwoPaneScreen {{
        background: #000080;
    }}

    #tps-title-bar {{
        background: {PANEL_FILL};
        height: 3;
        border-bottom: solid #aaaaff;
        padding: 0 2;
    }}

    #tps-title {{
        color: #aaaaff;
        text-style: bold;
        width: 1fr;
        height: 3;
        content-align: left middle;
    }}

    #tps-date {{
        color: #aaaaaa;
        height: 3;
        content-align: right middle;
        width: 14;
    }}

    #tps-body {{
        height: 1fr;
    }}

    #tps-left {{
        width: 33%;
        border-right: solid {BORDER_STRUCTURAL};
        background: #000066;
    }}

    #tps-right {{
        width: 1fr;
    }}
    """

    def compose(self) -> ComposeResult:
        """Render the standard title bar, split body, and footer."""
        with Horizontal(id="tps-title-bar"):
            yield Static(self.SCREEN_TITLE, id="tps-title")
            yield Static("", id="tps-date")
        with Horizontal(id="tps-body"):
            yield from self._compose_left_pane()
            yield from self._compose_right_pane()
        yield SplitFooter(self._CONTEXTUAL_ACTIONS)

    def on_mount(self) -> None:
        """Populate the effective date label."""
        self.query_one("#tps-date", Static).update(
            str(self.app.effective_date)  # type: ignore[attr-defined]
        )

    def _compose_left_pane(self) -> ComposeResult:
        """Yield the left pane widget. Override in subclasses.

        The outermost yielded widget must use ``id="tps-left"`` so that the
        base class CSS ``#tps-left { width: 33%; ... }`` applies.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement _compose_left_pane()")

    def _compose_right_pane(self) -> ComposeResult:
        """Yield the right pane content. Override in subclasses.

        The outermost yielded widget must use ``id="tps-right"`` so that the
        base class CSS ``#tps-right { width: 1fr; ... }`` applies.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement _compose_right_pane()")
