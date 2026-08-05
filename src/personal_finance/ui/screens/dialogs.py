"""Shared modal dialogs used across multiple screens.

Implements:
- ConfirmationDialog (Flow F-25)
- ErrorDialog       (Flow F-24)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Select, Static


class ModalDialogMixin:
    """Up/down field navigation for form-style modal dialogs.

    Mix this in alongside ``ModalScreen`` on any dialog that contains input
    fields navigable by arrow keys. The Select-expanded guard prevents
    interfering with open dropdown menus.

    Contract for subclasses: ``on_mount`` MUST call ``.focus()`` on the first
    interactive element. Textual never auto-focuses inside a modal — without an
    explicit call the focus lands on an invisible container and keyboard
    interaction is broken until the user presses Tab.
    """

    def on_key(self, event: Key) -> None:
        """Navigate fields with up/down arrows; F10 activates the primary button."""
        if event.key == "f10":
            for btn in self.query(Button):  # type: ignore[attr-defined]
                if btn.variant == "primary" and not btn.disabled:
                    btn.press()
                    event.stop()
                    return
        elif event.key in ("down", "up"):
            if any(sel.expanded for sel in self.query(Select)):  # type: ignore[attr-defined]
                return
            if event.key == "down":
                self.focus_next()  # type: ignore[attr-defined]
            else:
                self.focus_previous()  # type: ignore[attr-defined]
            event.stop()


class ConfirmationDialog(ModalScreen[bool]):
    """Modal confirmation dialog — Flow F-25.

    Presents a yes/no question and returns a boolean result.

    Args:
        question: The prompt to display (e.g. "Discard account 'Chequing'?").
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, question: str) -> None:
        """Store the question text."""
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        """Render the dialog."""
        with Vertical(classes="dialog"):
            yield Static(self._question, classes="dialog--question")
            with Horizontal(classes="dialog--buttons"):
                yield Button("Yes", id="btn-yes", variant="error")
                yield Button("No", id="btn-no", variant="primary")

    def on_mount(self) -> None:
        """Default focus to 'No' (safe default for destructive actions)."""
        self.query_one("#btn-no", Button).focus()

    def on_key(self, event: Key) -> None:
        """Left/Right arrows navigate between buttons in the button row."""
        if event.key == "right":
            self.focus_next()
            event.stop()
        elif event.key == "left":
            self.focus_previous()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismiss with True for Yes, False for No."""
        self.dismiss(event.button.id == "btn-yes")

    def action_cancel(self) -> None:
        """Esc cancels the dialog."""
        self.dismiss(False)


class ErrorDialog(ModalScreen[None]):
    """Modal error / warning dialog — Flow F-24.

    Args:
        message: Human-readable error description.
        title: Dialog title (defaults to "Error").
    """

    BINDINGS = [
        Binding("escape", "dismiss_dialog", "OK", show=False),
        Binding("enter", "dismiss_dialog", "OK", show=False),
    ]

    def __init__(self, message: str, title: str = "Error") -> None:
        """Store the message and title."""
        super().__init__()
        self._message = message
        self._title = title

    def compose(self) -> ComposeResult:
        """Render the dialog."""
        with Vertical(classes="dialog"):
            yield Static(f"[✗] {self._title}", classes="dialog--title")
            yield Static(self._message, classes="dialog--question")
            with Horizontal(classes="dialog--buttons"):
                yield Button("OK", id="btn-ok", variant="primary")

    def on_mount(self) -> None:
        """Default focus to OK."""
        self.query_one("#btn-ok", Button).focus()

    def on_button_pressed(self, _: Button.Pressed) -> None:
        """Dismiss the dialog."""
        self.dismiss()

    def action_dismiss_dialog(self) -> None:
        """Keyboard shortcut: Enter or Esc dismisses."""
        self.dismiss()
