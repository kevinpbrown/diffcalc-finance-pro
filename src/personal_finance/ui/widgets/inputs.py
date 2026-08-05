"""Shared input widgets for the Personal Finance TUI."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.events import Key
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Checkbox, Input, RadioSet, Select, Static


class RightAlignedNumericInput(Input):
    """Input that right-aligns its value within the content area.

    Textual's built-in Input always renders text left-aligned regardless of
    CSS ``text-align``. This subclass overrides ``render_line`` to prepend
    blank space when the value is shorter than the content area.

    Also enforces the application-wide convention that pressing Enter advances
    focus to the next focusable widget (same behaviour as Tab). This fires
    before the event bubbles, so parent ``on_input_submitted`` handlers still
    run — but they should NOT call ``focus_next()`` themselves to avoid a
    double-advance.

    Subclasses that need to reformat the displayed value on submit should
    override :meth:`_reformat` rather than ``on_input_submitted``. Textual's
    ``_get_dispatch_methods`` calls every class in the MRO that defines
    ``on_input_submitted``, so defining it in both a subclass and this base
    class would fire ``focus_next()`` twice.
    """

    def on_key(self, event: Key) -> None:
        """Advance or retreat focus with Up/Down (same as Shift+Tab/Tab)."""
        if event.key == "down":
            event.stop()
            self.screen.focus_next()
        elif event.key == "up":
            event.stop()
            self.screen.focus_previous()

    def _reformat(self) -> None:
        """Reformat the displayed value on submit. Override in subclasses."""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Reformat via subclass hook, then advance focus to the next field."""
        self._reformat()
        self.screen.focus_next()

    def render_line(self, y: int) -> Strip:
        """Render a single horizontal line with right-aligned value padding."""
        strip = super().render_line(y)
        if y != 0 or not self.value:
            return strip
        scroll_x, _ = self.scroll_offset
        if scroll_x != 0:
            return strip
        max_content_width = self.scrollable_content_region.width
        value_width = cell_len(self.value)
        cursor_width = 1 if (self.has_focus and self._cursor_visible) else 0
        occupied = value_width + cursor_width
        if occupied >= max_content_width:
            return strip
        left_pad = max_content_width - occupied
        text_strip = strip.crop(0, occupied)
        return Strip.blank(left_pad, self.rich_style) + text_strip


class TextInput(Input):
    """Left-aligned text input with Enter→next-field and Up/Down navigation.

    Drop-in replacement for ``Input`` on free-text fields (names, labels) that
    should participate in the application-wide keyboard navigation convention.
    """

    def on_key(self, event: Key) -> None:
        """Advance or retreat focus with Up/Down (same as Shift+Tab/Tab)."""
        if event.key == "down":
            event.stop()
            self.screen.focus_next()
        elif event.key == "up":
            event.stop()
            self.screen.focus_previous()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Advance focus to the next field when Enter is pressed."""
        self.screen.focus_next()


class MoneyInput(RightAlignedNumericInput):
    """Monetary input displayed as '$ 1,234.56'; reformats on Enter.

    Always two decimal places. Parses values that include a leading ``$``
    or comma separators, so the user can paste in formatted amounts.

    Callers use :meth:`format` to produce the initial ``value`` string and
    :meth:`parse` when reading the value back out (e.g. in save handlers).
    """

    DEFAULT_CSS = """
    MoneyInput {
        padding: 0 1;
    }
    """

    @staticmethod
    def format(value: Decimal | None, *, placeholder: str = "") -> str:
        """Return ``'$ X,XXX.XX'`` or ``placeholder`` when ``value`` is ``None``."""
        if value is None:
            return placeholder
        return f"$ {value:,.2f}"

    @staticmethod
    def parse(text: str) -> Decimal:
        """Strip ``$``, commas, and surrounding whitespace; parse as Decimal.

        Args:
            text: Raw input value, e.g. ``'$ 1,234.56'`` or ``'1234.56'``.

        Returns:
            Parsed Decimal.

        Raises:
            InvalidOperation: If ``text`` cannot be parsed as a Decimal.
        """
        cleaned = text.strip().lstrip("$").strip().replace(",", "")
        return Decimal(cleaned)

    def _reformat(self) -> None:
        try:
            self.value = self.format(self.parse(self.value))
        except (InvalidOperation, Exception):
            pass

    def render_line(self, y: int) -> Strip:
        """Render with '$ ' pinned at the left edge and numeric part right-aligned."""
        if y != 0 or not self.value or not self.value.startswith("$ "):
            return super().render_line(y)
        scroll_x, _ = self.scroll_offset
        if scroll_x != 0:
            return super().render_line(y)

        # Get Input's default left-aligned rendering (bypassing right-align logic)
        base_strip = super(RightAlignedNumericInput, self).render_line(y)

        max_content_width = self.scrollable_content_region.width
        numeric_part = self.value[2:]  # everything after "$ "
        cursor_width = 1 if (self.has_focus and self._cursor_visible) else 0
        numeric_width = cell_len(numeric_part)

        if 2 + numeric_width + cursor_width >= max_content_width:
            return base_strip  # no room to add spacing, fall back

        middle_spaces = max_content_width - 2 - numeric_width - cursor_width
        dollar_strip = base_strip.crop(0, 2)
        numeric_strip = base_strip.crop(2, 2 + numeric_width + cursor_width)
        return dollar_strip + Strip.blank(middle_spaces, self.rich_style) + numeric_strip


class PercentInput(RightAlignedNumericInput):
    """Percentage input displayed as 'N.N%' (whole-number entry); reformats on Enter.

    The user types whole numbers (e.g. ``3.5``); the widget displays ``3.5%``.
    Trailing zeros are trimmed: ``3.00`` → ``3%``, ``3.50`` → ``3.5%``.

    The widget stores and returns the whole-number value (e.g. ``Decimal('3.5')``).
    Callers are responsible for dividing by 100 when a fraction is needed for
    service calls (e.g. discount rates).
    """

    @staticmethod
    def format(value: Decimal | None, *, placeholder: str = "") -> str:
        """Return ``'N.N%'`` with trailing zeros trimmed, or ``placeholder``."""
        if value is None:
            return placeholder
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return f"{text}%"

    @staticmethod
    def parse(text: str) -> Decimal:
        """Strip trailing ``%`` and surrounding whitespace; parse as Decimal.

        Args:
            text: Raw input value, e.g. ``'3.5%'`` or ``'3.5'``.

        Returns:
            Parsed Decimal (whole number, e.g. ``Decimal('3.5')``).

        Raises:
            InvalidOperation: If ``text`` cannot be parsed as a Decimal.
        """
        cleaned = text.strip().rstrip("%").strip()
        return Decimal(cleaned or "0")

    def _reformat(self) -> None:
        try:
            self.value = self.format(self.parse(self.value))
        except (InvalidOperation, Exception):
            pass


class QuantityInput(RightAlignedNumericInput):
    """Quantity input for share counts; integers display without decimals.

    Whole quantities display as ``'100'``; fractional shares display with up
    to four decimal places (trailing zeros stripped), e.g. ``'50.5'``.
    """

    @staticmethod
    def format(value: Decimal | None) -> str:
        """Return integer or up to 4-decimal-place representation."""
        if value is None:
            return ""
        if value == value.to_integral_value():
            return f"{value:,.0f}"
        return f"{value:,.4f}".rstrip("0")

    @staticmethod
    def parse(text: str) -> Decimal:
        """Strip commas and surrounding whitespace; parse as Decimal.

        Args:
            text: Raw input value, e.g. ``'1,000'`` or ``'50.5'``.

        Returns:
            Parsed Decimal.

        Raises:
            InvalidOperation: If ``text`` cannot be parsed as a Decimal.
        """
        return Decimal(text.strip().replace(",", ""))

    def _reformat(self) -> None:
        try:
            self.value = self.format(self.parse(self.value))
        except (InvalidOperation, Exception):
            pass


class AppRadioSet(RadioSet):
    """RadioSet with Enter→next-field and Space/arrows→navigate-and-select behaviour.

    The built-in RadioSet binds both ``enter`` and ``space`` to toggle the
    current button. This subclass intercepts Enter before the binding fires so
    it advances focus instead, matching the application-wide navigation
    convention. Arrow keys still navigate between options; Space still toggles.
    """

    async def _on_key(self, event: Key) -> None:
        """Advance focus on Enter; leave arrows and Space to work as normal."""
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.screen.focus_next()


class AppCheckbox(Checkbox):
    """Checkbox with 'Space toggles, Enter advances' keyboard behaviour.

    The built-in Checkbox binds both ``enter`` and ``space`` to toggle.
    This subclass intercepts Enter before the binding fires so it advances
    focus instead, matching the application-wide navigation convention.
    """

    async def _on_key(self, event: Key) -> None:
        """Advance focus on Enter; leave Space to toggle as normal."""
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.screen.focus_next()


class AppSelect(Select):  # type: ignore[type-arg]
    """Select widget with 'Space/Down opens, Enter advances' keyboard behaviour.

    When the dropdown is **closed**, pressing Enter advances focus to the next
    field instead of opening the dropdown. Space and the Down arrow still open
    the dropdown in the normal Textual way.

    When the dropdown is **open**, all keys behave as in the standard Select.

    When the overlay would overflow the right edge of the screen, it is
    repositioned so that its right edge aligns with the right edge of the
    closed Select box, opening to the left instead.
    """

    async def _on_key(self, event: Key) -> None:
        """Intercept Enter-when-closed to advance focus instead of opening."""
        if event.key == "enter" and not self.expanded:
            event.prevent_default()
            event.stop()
            self.screen.focus_next()

    def __class_getitem__(cls, item: object) -> object:
        """Support ``AppSelect[T]`` generic syntax for type annotations."""
        return cls

    def watch_expanded(self, expanded: bool) -> None:
        """Snap overlay's right edge to select's right edge on overflow."""
        if expanded:
            self.call_after_refresh(self._snap_overlay_x)

    def _snap_overlay_x(self) -> None:
        from textual.widgets._select import SelectOverlay  # noqa: PLC0415

        try:
            overlay = self.query_one(SelectOverlay)
        except Exception:
            return
        ol_width = overlay.region.width
        if ol_width == 0:
            return
        screen_width = self.screen.size.width
        # Natural x of the overlay equals the select widget's left edge.
        natural_right = self.region.x + ol_width
        if natural_right <= screen_width:
            # No overflow — reset any previous offset so it stays left-aligned.
            overlay.styles.offset = (0, 0)
        else:
            # Overflow — shift left so overlay.right == select.right.
            new_x = max(0, self.region.right - ol_width)
            overlay.styles.offset = (new_x - self.region.x, 0)


class GoldBorderDisplay(Static):
    """Focusable gold-bordered read-only display cell.

    Used for fields that are conceptually editable through a dialog (opened
    with ``F6``) rather than inline. Press ``Enter`` to advance focus; ``F6``
    bubbles up to the owning screen's action binding to open the dialog.

    Width is determined by the parent layout. The caller is responsible for
    setting an appropriate width via CSS classes or inline styles.
    """

    can_focus = True

    DEFAULT_CSS = """
    GoldBorderDisplay {
        height: 3;
        border: solid #aa8800;
        content-align: left middle;
        padding: 0 1;
        color: #aaaaaa;
    }
    GoldBorderDisplay:focus {
        border: solid #ffd700;
        color: #ffffff;
    }
    """

    def render_line(self, y: int) -> Strip:
        """Render with '$ ' at the left edge and numeric part right-aligned.

        Textual calls render_line with content-relative y (gutter already
        subtracted), so y=0 is the single content line, not the border line.
        The strip returned is content-only — no border/padding chars.
        """
        strip = super().render_line(y)
        if y != 0:
            return strip
        value = str(self.content)
        if not value.startswith("$ "):
            return strip
        # self.size is already the content-region size for a Static
        # (border and padding excluded), so use it directly.
        content_width = self.size.width
        numeric_part = value[2:]
        spaces = content_width - 2 - cell_len(numeric_part)
        if spaces < 0:
            return strip
        dollar_strip = strip.crop(0, 2)
        numeric_strip = strip.crop(2, 2 + cell_len(numeric_part))
        return dollar_strip + Strip.blank(spaces, self.rich_style) + numeric_strip

    def on_key(self, event: Key) -> None:
        """Advance focus on Enter; F6 bubbles to the screen's binding."""
        if event.key == "enter":
            event.stop()
            self.screen.focus_next()


class F6OpenableField(Widget):
    """Numeric field that toggles between editable and gold-bordered read-only.

    In **editable** mode a :class:`MoneyInput` is shown. The parent widget is
    responsible for handling ``Input.Submitted`` (the event bubbles past this
    container since ``can_focus`` is ``False``).

    In **read-only** mode a :class:`GoldBorderDisplay` is shown; pressing
    ``Enter`` advances focus.

    In **both** modes pressing ``F6`` bubbles to the owning screen's action
    binding so the screen can open the appropriate dialog.

    Call :meth:`set_state` to switch modes at runtime (e.g. after a dialog saves).

    Width is determined by the parent layout; set it via a CSS class on the
    instance rather than in ``DEFAULT_CSS``.
    """

    can_focus = False  # focus lives in the active child widget

    DEFAULT_CSS = """
    F6OpenableField {
        height: 3;
    }
    F6OpenableField MoneyInput {
        width: 100%;
        height: 3;
    }
    F6OpenableField GoldBorderDisplay {
        width: 100%;
        height: 3;
    }
    """

    def __init__(
        self,
        initial_value: str,
        *,
        editable: bool,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Store the initial value and editable state.

        Args:
            initial_value: Text to display in the field.
            editable: If ``True``, start in editable (Input) mode; otherwise
                start in gold-bordered read-only (GoldBorderDisplay) mode.
            id: Optional Textual widget ID.
            classes: Optional space-separated CSS class names.
        """
        super().__init__(id=id, classes=classes)
        self._value = initial_value
        self._editable = editable

    def compose(self) -> ComposeResult:
        """Yield both child widgets; visibility is controlled in on_mount."""
        yield MoneyInput(value=self._value)
        yield GoldBorderDisplay(self._value)

    def on_mount(self) -> None:
        """Show the correct child widget based on the initial editable state."""
        self._apply_state()

    def set_state(self, editable: bool, value: str) -> None:
        """Switch between editable and read-only modes with a new display value.

        Safe to call before or after mounting; if not yet mounted the new state
        will be applied in :meth:`on_mount`.

        Args:
            editable: ``True`` to show the editable Input; ``False`` to show the
                gold-bordered read-only display.
            value: New text to display in whichever child becomes visible.
        """
        self._editable = editable
        self._value = value
        if self.is_mounted:
            inp = self.query_one(MoneyInput)
            disp = self.query_one(GoldBorderDisplay)
            inp.value = value
            disp.update(value)
            self._apply_state()

    def _apply_state(self) -> None:
        inp = self.query_one(MoneyInput)
        disp = self.query_one(GoldBorderDisplay)
        inp.display = self._editable
        disp.display = not self._editable
