"""SplitFooter widget — footer with constant bindings left, contextual bindings right."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static
from textual.widgets._footer import FooterKey

from personal_finance.ui.palette import PANEL_FILL


class SplitFooter(Widget, can_focus=False, can_focus_children=False):
    """Footer that left-aligns constant bindings and right-aligns contextual ones.

    Pass the set of contextual action names at construction time. All other
    visible bindings are treated as constant and placed on the left. Contextual
    bindings (row-level operations that depend on the focused item) are placed
    on the right, separated by a flexible spacer.

    The widget subscribes to the screen's ``bindings_updated_signal`` so it
    recomposes automatically whenever ``refresh_bindings()`` is called.
    """

    DEFAULT_CSS = f"""
    SplitFooter {{
        layout: horizontal;
        background: {PANEL_FILL};
        color: $footer-foreground;
        dock: bottom;
        height: 1;
    }}
    SplitFooter #footer-spacer {{
        width: 1fr;
        height: 1;
        background: {PANEL_FILL};
    }}
    SplitFooter FooterKey {{
        margin-right: 1;
    }}
    """

    def __init__(self, contextual_actions: frozenset[str] | set[str]) -> None:
        """Initialise with the set of action names to treat as contextual (right-aligned)."""
        super().__init__()
        self._contextual_actions = frozenset(contextual_actions)
        self._bindings_ready = False

    def on_mount(self) -> None:
        """Subscribe to bindings signal and trigger initial render."""
        self.screen.bindings_updated_signal.subscribe(self, self.bindings_changed)
        self._bindings_ready = True
        self.call_after_refresh(self.recompose)

    def on_unmount(self) -> None:
        """Unsubscribe from bindings signal on teardown."""
        self.screen.bindings_updated_signal.unsubscribe(self)

    def bindings_changed(self, screen: Screen[object]) -> None:
        """Called when screen bindings change; triggers a recompose."""
        self._bindings_ready = True
        if self.is_attached and screen is self.screen:
            self.call_after_refresh(self.recompose)

    def compose(self) -> ComposeResult:
        """Yield constant bindings, a flexible spacer, then contextual bindings."""
        if not self._bindings_ready:
            return

        active_bindings = self.screen.active_bindings
        constant: list[FooterKey] = []
        contextual: list[FooterKey] = []
        seen_actions: set[str] = set()

        for key, active in active_bindings.items():
            binding = active.binding
            if not binding.show:
                continue
            if binding.action in seen_actions:
                continue
            seen_actions.add(binding.action)

            key_widget = FooterKey(
                key=key,
                key_display=self.app.get_key_display(binding),
                description=binding.description,
                action=binding.action,
                disabled=not active.enabled,
                tooltip=active.tooltip or binding.description,
            )
            if binding.action in self._contextual_actions:
                contextual.append(key_widget)
            else:
                constant.append(key_widget)

        yield from constant
        yield Static("", id="footer-spacer")
        yield from contextual
