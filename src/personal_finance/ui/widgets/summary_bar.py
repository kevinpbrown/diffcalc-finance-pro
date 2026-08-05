"""SummaryBar widget — fixed horizontal bar below a scrollable content area."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from personal_finance.ui.palette import PANEL_FILL


class SummaryBar(Widget):
    """Horizontal summary bar styled to match the app footer palette.

    Displays one or more labelled values in a dark-blue bar with a top
    border, sitting between a scrollable content area and the footer.

    ``items`` is a list of ``(suffix, initial_text, width)`` tuples:

    * ``suffix``       — unique id fragment; the underlying ``Static`` gets
                         id ``"sb-<suffix>"``.
    * ``initial_text`` — text shown before data loads (often empty).
    * ``width``        — ``"fill"`` for a 1fr left-aligned column, or an
                         ``int`` for a fixed-width right-aligned column.

    Call :meth:`update_item` to refresh individual cells after data loads.
    """

    DEFAULT_CSS = f"""
    SummaryBar {{
        layout: horizontal;
        background: {PANEL_FILL};
        border-top: solid #aaaaff;
        height: auto;
        padding: 0 2 1 2;
    }}
    SummaryBar .sb-item {{
        color: #ffffff;
        height: 1;
    }}
    SummaryBar .sb-fill {{
        width: 1fr;
    }}
    """

    def __init__(
        self,
        items: list[tuple[str, str, int | str]],
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Store items for compose."""
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self._items = items

    def compose(self) -> ComposeResult:
        """Render one Static per item with the requested width and alignment."""
        for suffix, text, width in self._items:
            s = Static(text, id=f"sb-{suffix}", classes="sb-item")
            if width == "fill":
                s.add_class("sb-fill")
            else:
                s.styles.width = width
                s.styles.text_align = "right"
            yield s

    def update_item(self, suffix: str, text: str) -> None:
        """Update the text of a single item by its suffix."""
        self.query_one(f"#sb-{suffix}", Static).update(text)
