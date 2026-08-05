"""DateInput widget — YYYY-MM-DD masked text input with live validation.

Textual does not ship a calendar or date-picker widget; per TUI Principles §3
we use a plain MaskedInput with immediate parse-on-change validation.

Note: The inner message class is named ``DateChanged`` (not ``Changed``) because
Textual dispatches ``self.Changed(...)`` when the reactive value changes, so any
inner class named ``Changed`` on a MaskedInput subclass would shadow the base
class's dispatch and receive the wrong arguments.
"""

from __future__ import annotations

from datetime import date

from textual.events import Key
from textual.message import Message
from textual.validation import ValidationResult, Validator
from textual.widgets import MaskedInput


class _DateValidator(Validator):
    """Validates that the entered string parses as a valid YYYY-MM-DD date."""

    def validate(self, value: str) -> ValidationResult:
        """Return failure when ``value`` is not a valid calendar date.

        Args:
            value: The raw string from the MaskedInput (may contain underscores
                from the mask for unfilled positions).
        """
        clean = value.replace("_", "")
        if len(clean) < 10:
            return self.failure("Date must be YYYY-MM-DD")
        try:
            date.fromisoformat(clean)
        except ValueError:
            return self.failure(f"{value!r} is not a valid date (YYYY-MM-DD)")
        return self.success()


class DateInput(MaskedInput):
    """A YYYY-MM-DD date input widget with immediate validation.

    Emits ``DateInput.DateChanged`` when the user commits a valid date (navigates
    away from a fully-entered, valid value).

    Usage::

        yield DateInput(value="2026-05-26", id="effective-date")
    """

    class DateChanged(Message):
        """Posted when the user commits a valid date value.

        Attributes:
            date_input: The ``DateInput`` widget that changed.
            value: The new date.
        """

        def __init__(self, date_input: DateInput, value: date) -> None:
            """Create message with the source widget and parsed date."""
            super().__init__()
            self.date_input = date_input
            self.value = value

        @property
        def control(self) -> DateInput:
            """The ``DateInput`` that emitted this message."""
            return self.date_input

    def __init__(
        self,
        value: date | str | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialise with optional starting value.

        Args:
            value: Initial date as a ``date`` object or ``YYYY-MM-DD`` string.
                Defaults to today when ``None``.
            id: Widget DOM id.
            classes: Widget CSS classes.
        """
        initial = value if isinstance(value, str) else (value or date.today()).isoformat()
        super().__init__(
            template="9999-99-99",
            value=initial,
            validators=[_DateValidator()],
            id=id,
            classes=classes,
        )
        self._committed_value: str = initial

    def on_mount(self) -> None:
        """Store the initial committed value."""
        self._committed_value = self.value

    def validate_value(self, value: str) -> str:
        """Return current value unchanged when the proposed value can't match the mask.

        MaskedInput.validate_value raises ValueError when ``value`` doesn't fit
        the template (e.g. a letter typed while all digits are selected).  We
        catch that here and return the existing value so Input._on_key's
        subsequent ``event.prevent_default()`` call is reached without crashing.
        """
        try:
            return super().validate_value(value)
        except ValueError:
            return self.value

    def on_blur(self) -> None:
        """On focus loss, either commit valid date or revert invalid entry."""
        result = self.validate(self.value)
        if result is not None and result.is_valid:
            clean = self.value.replace("_", "")
            parsed = date.fromisoformat(clean)
            self._committed_value = clean
            self.post_message(DateInput.DateChanged(self, parsed))
        else:
            self.value = self._committed_value

    async def action_submit(self) -> None:
        """Enter moves focus forward (on_blur handles commit or revert)."""
        self.screen.focus_next()

    def on_key(self, event: Key) -> None:
        """Revert to committed value when the user presses Esc mid-edit.

        ``event.stop()`` prevents Escape from also triggering the screen-level
        quit binding while the user is editing the date field.
        """
        if event.key == "escape":
            self.value = self._committed_value
            event.stop()

    @property
    def date(self) -> date | None:
        """Return the current value as a ``date``, or ``None`` if invalid."""
        try:
            clean = self.value.replace("_", "")
            return date.fromisoformat(clean)
        except ValueError:
            return None
