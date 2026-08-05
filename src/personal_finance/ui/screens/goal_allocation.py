"""Goal Allocation View screen — Flow F-11b.

Displays a 33/67 split view: the left pane lists all active goals (navigable
with Up/Down); the right pane shows target vs actual asset-class allocations
for the currently selected goal.

Target percentages are editable inline. Changes are held in memory and saved
in bulk with F7 (G-OP-8). Navigating away while dirty prompts a
ConfirmationDialog.

Footer actions:
  F3  → GoalsListScreen (Summary View), with selected goal pre-focused
  F7  → Save in-memory target changes for the selected goal (contextual)
  Esc → GoalsListScreen (same as F3 — Esc is "back", not "escape to root")
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

import structlog
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.events import Key
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Input, LoadingIndicator, Static

from personal_finance.service.application.goal_app_service import (
    GoalAllocationData,
    GoalListItem,
)
from personal_finance.ui.palette import BORDER_STRUCTURAL, PANEL_FILL, TEXT_DIM
from personal_finance.ui.screens.dialogs import ConfirmationDialog
from personal_finance.ui.widgets.inputs import PercentInput
from personal_finance.ui.widgets.split_footer import SplitFooter

logger = structlog.get_logger(__name__)

_D100 = Decimal("100")
_D0 = Decimal("0")


# ── Formatting helpers ─────────────────────────────────────────────────────────


def _fmt_pct(value: Decimal) -> str:
    """Format a percentage Decimal, stripping trailing zeros (e.g. '3%', '3.5%')."""
    return f"{value.normalize():f}%"


def _fmt_diff(pct: Decimal, amt: Decimal) -> str:
    """Format a target/actual difference without color markup."""
    sign_pct = "+" if pct >= _D0 else ""
    sign_amt = "+" if amt >= _D0 else "-"
    return f"{sign_amt}${abs(amt):,.0f} ({sign_pct}{pct.normalize():f}%)"


def _colored_diff(pct: Decimal, amt: Decimal) -> str:
    """Format difference with Rich color markup: green if positive, red if negative."""
    text = _fmt_diff(pct, amt)
    if pct > _D0:
        return f"[green]{text}[/]"
    if pct < _D0:
        return f"[red]{text}[/]"
    return text


def _fmt_amt(value: Decimal) -> str:
    """Format a whole-dollar amount with '$' pinned left, digits right-justified.

    Fixed-width (11 chars, e.g. '$ 9,999,999') to match the input-box convention
    used elsewhere (``MoneyInput``/``GoldBorderDisplay``): the sign stays put and
    only the digits shift, so amounts line up in a column regardless of magnitude.
    """
    return f"$ {value:>9,.0f}"


def _fmt_actual_pct(value: Decimal) -> str:
    """Format the Actual % column: nearest tenth of a percent, always one decimal."""
    return f"{value:.1f}%"


# ── Left-pane widget ───────────────────────────────────────────────────────────


class _GoalListPane(Widget):
    """Left pane: read-only goal list rendered as a single Rich Text renderable.

    Using ``render()`` rather than child widgets avoids async DOM-mutation
    complexity; ``update()`` just calls ``self.refresh()`` which is always safe
    to call from any context.

    Up/Down navigation is handled in the owning :class:`GoalAllocationView`
    screen (via ``on_key``), not here.
    """

    can_focus = True

    DEFAULT_CSS = """
    _GoalListPane {
        width: 1fr;
        height: 1fr;
        padding: 1 1;
        overflow-y: auto;
    }
    _GoalListPane:focus {
        border-left: solid #aaaaff;
    }
    """

    def __init__(self, id: str | None = None) -> None:
        """Initialise with an empty list."""
        super().__init__(id=id)
        self._items: list[GoalListItem] = []
        self._selected_idx: int = 0

    def update(self, items: list[GoalListItem], selected_idx: int) -> None:
        """Replace the displayed goal list and trigger a repaint."""
        self._items = items
        self._selected_idx = selected_idx
        self.refresh()

    def render(self) -> Text:
        """Build the Rich Text renderable for the goal list."""
        text = Text()
        for i, item in enumerate(self._items):
            cursor = ">" if i == self._selected_idx else " "
            warning = " [!]" if item.target_sum_exceeds_100 else ""
            line = f"{cursor} {item.name}{warning}"
            style = "bold white" if i == self._selected_idx else TEXT_DIM
            text.append(line, style=style)
            if i < len(self._items) - 1:
                text.append("\n")
        return text


# ── Allocation row widget ──────────────────────────────────────────────────────


class _AllocationRow(Widget):
    """One asset-class row: Name | [Target%] % | Actual % | Actual $ | Difference."""

    DEFAULT_CSS = """
    _AllocationRow {
        layout: horizontal;
        height: 3;
        padding: 0 1;
    }
    _AllocationRow .ar-name {
        width: 1fr;
        min-width: 10;
        content-align: left middle;
        color: #aaaaaa;
    }
    _AllocationRow .ar-target {
        width: 14;
        height: 3;
    }
    _AllocationRow .ar-actual-amt {
        width: 12;
        height: 3;
        margin-left: 1;
        content-align: left middle;
        color: #aaaaaa;
        padding-right: 1;
    }
    _AllocationRow .ar-actual-pct {
        width: 8;
        height: 3;
        content-align: right middle;
        color: #aaaaaa;
    }
    _AllocationRow .ar-diff {
        width: 22;
        height: 3;
        content-align: right middle;
        color: #aaaaaa;
    }
    """

    def __init__(
        self,
        asset_class_id: int,
        asset_class_name: str,
        target_initial: str,
        actual_pct_text: str,
        actual_amt_text: str,
        diff_text: str,
    ) -> None:
        """Store the row's display values."""
        super().__init__()
        self._ac_id: int = asset_class_id
        self._name: str = asset_class_name
        self._target_initial: str = target_initial
        self._actual_pct_text: str = actual_pct_text
        self._actual_amt_text: str = actual_amt_text
        self._diff_text: str = diff_text

    def compose(self) -> ComposeResult:
        """Render the five-column row."""
        yield Static(self._name, classes="ar-name")
        yield PercentInput(
            value=self._target_initial,
            id=f"target-{self._ac_id}",
            classes="ar-target",
        )
        yield Static(self._actual_amt_text, classes="ar-actual-amt")
        yield Static(self._actual_pct_text, classes="ar-actual-pct")
        yield Static(self._diff_text, classes="ar-diff")

    def update_diff(self, diff_text: str) -> None:
        """Refresh the Difference column text in-place."""
        self.query_one(".ar-diff", Static).update(diff_text)


# ── Column headers widget ──────────────────────────────────────────────────────


class _AllocationHeaders(Widget):
    """Column header bar for the right-pane allocation table."""

    DEFAULT_CSS = """
    _AllocationHeaders {
        layout: horizontal;
        height: 1;
        padding: 0 1;
    }
    _AllocationHeaders .ah-name {
        width: 1fr;
        min-width: 10;
        text-style: bold;
    }
    _AllocationHeaders .ah-target {
        width: 14;
        text-style: bold;
    }
    _AllocationHeaders .ah-actual-amt {
        width: 12;
        margin-left: 1;
        text-style: bold;
        padding-right: 1;
    }
    _AllocationHeaders .ah-actual-pct {
        width: 8;
        text-style: bold;
    }
    _AllocationHeaders .ah-diff {
        width: 22;
        text-style: bold;
        content-align: right middle;
    }
    """

    def compose(self) -> ComposeResult:
        """Render column header labels."""
        yield Static("Name", classes="ah-name")
        yield Static("Target", classes="ah-target")
        yield Static("Actual $", classes="ah-actual-amt")
        yield Static("Actual %", classes="ah-actual-pct")
        yield Static("Difference", classes="ah-diff")


# ── Totals row widget ─────────────────────────────────────────────────────────


class _AllocationTotalsRow(Widget):
    """Totals row: sums Target % and Actual $; Actual % and Difference are excluded."""

    DEFAULT_CSS = """
    _AllocationTotalsRow {
        layout: horizontal;
        height: 1;
        padding: 0 1;
        margin-top: 1;
    }
    _AllocationTotalsRow .atr-name {
        width: 1fr;
        min-width: 10;
        text-style: bold;
        color: #aaaaaa;
    }
    _AllocationTotalsRow .atr-target {
        width: 14;
        content-align: right middle;
        text-style: bold;
    }
    _AllocationTotalsRow .atr-actual-amt {
        width: 12;
        margin-left: 1;
        padding-right: 1;
        text-style: bold;
    }
    _AllocationTotalsRow .atr-actual-pct {
        width: 8;
    }
    _AllocationTotalsRow .atr-diff {
        width: 22;
    }
    """

    def compose(self) -> ComposeResult:
        """Render the totals row with placeholder statics for live values."""
        yield Static("Total", classes="atr-name")
        yield Static("", id="atr-target-val", classes="atr-target")
        yield Static("", id="atr-actual-amt-val", classes="atr-actual-amt")
        yield Static("", classes="atr-actual-pct")
        yield Static("", classes="atr-diff")

    def update(self, target_pct_total: str, actual_amt_total: str) -> None:
        """Refresh the Target % and Actual $ totals."""
        self.query_one("#atr-target-val", Static).update(target_pct_total)
        self.query_one("#atr-actual-amt-val", Static).update(actual_amt_total)


# ── GoalAllocationView ─────────────────────────────────────────────────────────


class GoalAllocationView(Screen[None]):
    """Goal Allocation View — Flow F-11b."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("f3", "summary_view", "Summary View", show=True),
        Binding("f7", "save_targets", "Save Changes", show=True),
    ]

    DEFAULT_CSS = f"""
    GoalAllocationView {{
        background: #000080;
    }}

    #gav-title-bar {{
        background: {PANEL_FILL};
        height: 3;
        border-bottom: solid #aaaaff;
        padding: 0 2;
    }}

    #gav-title {{
        color: #aaaaff;
        text-style: bold;
        width: 1fr;
        height: 3;
        content-align: left middle;
    }}

    #gav-date {{
        color: #aaaaaa;
        height: 3;
        content-align: right middle;
        width: 14;
    }}

    #gav-body {{
        height: 1fr;
        background: #000080;
    }}

    #gav-left {{
        width: 33%;
        border-right: solid {BORDER_STRUCTURAL};
        background: #000066;
    }}

    #gav-right {{
        width: 1fr;
        padding: 0 1;
        overflow-y: auto;
    }}

    #gav-right-header {{
        height: 1;
        margin: 1 1 1 1;
        color: #aaaaff;
        text-style: bold;
    }}

    #gav-rows {{
        height: auto;
    }}

    #gav-warning {{
        height: 1;
        color: #ff4444;
        padding: 0 2;
        display: none;
    }}

    #gav-warning.visible {{
        display: block;
    }}
    """

    def __init__(self, initial_goal_id: int | None = None) -> None:
        """Initialise screen state.

        Args:
            initial_goal_id: Goal to select first; falls back to the first goal
                in the list when ``None``.
        """
        super().__init__()
        self._initial_goal_id = initial_goal_id
        self._goal_items: list[GoalListItem] = []
        self._selected_idx: int = 0
        self._allocation_data: GoalAllocationData | None = None
        self._persisted_targets: dict[int, Decimal] = {}
        self._actual_amt_total: Decimal = _D0
        self._dirty = False

    # ── Composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Render title bar, split body, and footer."""
        with Horizontal(id="gav-title-bar"):
            yield Static("Goal Allocations", id="gav-title")
            yield Static("", id="gav-date")
        with Horizontal(id="gav-body"):
            yield _GoalListPane(id="gav-left")
            with VerticalScroll(id="gav-right", can_focus=False):
                yield Static("", id="gav-right-header")
                yield _AllocationHeaders()
                with VerticalScroll(id="gav-rows", can_focus=False):
                    yield LoadingIndicator()
                yield _AllocationTotalsRow(id="gav-totals")
                yield Static("", id="gav-warning")
        yield SplitFooter({"save_targets"})

    def on_mount(self) -> None:
        """Display the effective date and kick off data loading."""
        self.query_one("#gav-date", Static).update(
            str(self.app.effective_date)  # type: ignore[attr-defined]
        )
        self.run_worker(self._load_goals(), exclusive=True, name="load-goal-list")

    # ── Binding visibility ────────────────────────────────────────────────────

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Control F7 Save Changes visibility.

        - Hidden when not dirty (``None``).
        - Shown-but-disabled when dirty and sum > 100% (``False``).
        - Enabled when dirty and sum ≤ 100% (``True``).
        """
        if action == "save_targets":
            if not self._dirty:
                return None
            return self._current_target_sum() <= _D100
        return True

    # ── Keyboard handling ─────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        """Navigate the goal list when the left pane has keyboard focus."""
        if not isinstance(self.focused, _GoalListPane):
            return
        if event.key == "down":
            event.stop()
            if self._goal_items:
                new_idx = min(self._selected_idx + 1, len(self._goal_items) - 1)
                if new_idx != self._selected_idx:
                    self._change_goal(new_idx)
        elif event.key == "up":
            event.stop()
            if self._goal_items:
                new_idx = max(self._selected_idx - 1, 0)
                if new_idx != self._selected_idx:
                    self._change_goal(new_idx)
        elif event.key == "enter":
            event.stop()
            self._focus_first_target_input()

    # ── Input change handler ──────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        """Track dirty state, refresh warning, and live-update the Difference cell."""
        if not (event.input.id or "").startswith("target-"):
            return
        self._update_dirty()
        self._update_warning()
        self._update_totals()
        self.refresh_bindings()
        self._update_row_diff(event.input)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_go_back(self) -> None:
        """Return to Summary View (Esc) — same navigation as F3."""
        self.action_summary_view()

    def action_summary_view(self) -> None:
        """Switch to GoalsListScreen (F3) with the selected goal pre-focused."""
        selected_goal_id = (
            self._goal_items[self._selected_idx].goal_id if self._goal_items else None
        )

        def go() -> None:
            from personal_finance.ui.screens.goals import GoalsListScreen  # noqa: PLC0415

            self.app.switch_screen(GoalsListScreen(initial_goal_id=selected_goal_id))

        self._navigate_if_clean(go)

    def action_save_targets(self) -> None:
        """Persist in-memory Target% edits via G-OP-8 (F7)."""
        if not self._allocation_data or not self._dirty:
            return
        if self._current_target_sum() > _D100:
            self.notify(
                "Target percentages exceed 100% — reduce them before saving.",
                severity="error",
                timeout=4,
            )
            return
        self.run_worker(self._do_save_targets(), exclusive=False, name="save-targets")

    # ── Dirty-flag navigation guard ───────────────────────────────────────────

    def _navigate_if_clean(self, action_fn: Callable[[], object]) -> None:
        """Run ``action_fn`` directly, or prompt to discard changes when dirty."""
        if self._dirty:

            def on_confirmed(result: bool | None) -> None:
                if result:
                    self._dirty = False
                    action_fn()

            self.app.push_screen(
                ConfirmationDialog("Discard unsaved changes?"), callback=on_confirmed
            )
        else:
            action_fn()

    # ── Goal switching ────────────────────────────────────────────────────────

    def _change_goal(self, new_idx: int) -> None:
        """Switch the selected goal, prompting first when dirty."""

        def do_switch() -> None:
            self._selected_idx = new_idx
            self._dirty = False
            self.refresh_bindings()
            self.query_one("#gav-left", _GoalListPane).update(self._goal_items, self._selected_idx)
            self.run_worker(
                self._load_allocation_data(self._goal_items[new_idx].goal_id),
                exclusive=True,
                name="load-allocation",
            )

        self._navigate_if_clean(do_switch)

    # ── State helpers ─────────────────────────────────────────────────────────

    def _current_target_sum(self) -> Decimal:
        """Sum the current Target% input values for the right pane."""
        total = _D0
        if self._allocation_data is None:
            return total
        for row in self._allocation_data.rows:
            try:
                widget = self.query_one(f"#target-{row.asset_class_id}", PercentInput)
                total += PercentInput.parse(widget.value)
            except (InvalidOperation, Exception):
                pass
        return total

    def _update_dirty(self) -> None:
        """Recompute ``_dirty`` by comparing live inputs to ``_persisted_targets``."""
        if self._allocation_data is None:
            self._dirty = False
            return
        for row in self._allocation_data.rows:
            try:
                widget = self.query_one(f"#target-{row.asset_class_id}", PercentInput)
                current = PercentInput.parse(widget.value)
            except (InvalidOperation, Exception):
                self._dirty = True
                return
            if current != self._persisted_targets.get(row.asset_class_id, _D0):
                self._dirty = True
                return
        self._dirty = False

    def _update_totals(self) -> None:
        """Refresh the Target % and Actual $ totals row."""
        target_sum = self._current_target_sum()
        self.query_one("#gav-totals", _AllocationTotalsRow).update(
            target_pct_total=_fmt_pct(target_sum),
            actual_amt_total=_fmt_amt(self._actual_amt_total),
        )

    def _focus_first_target_input(self) -> None:
        """Move focus to the first Target% input in the right pane."""
        try:
            self.query_one("#gav-rows", VerticalScroll).query(Input).first(Input).focus()
        except Exception:
            pass

    def _update_row_diff(self, target_input: Input) -> None:
        """Recompute and refresh the Difference cell for the row owning target_input."""
        if self._allocation_data is None:
            return
        input_id = target_input.id or ""
        try:
            ac_id = int(input_id.removeprefix("target-"))
        except ValueError:
            return
        row_data = next((r for r in self._allocation_data.rows if r.asset_class_id == ac_id), None)
        if row_data is None:
            return
        try:
            new_target = PercentInput.parse(target_input.value)
        except (InvalidOperation, Exception):
            return
        if new_target == _D0:
            diff_text = "—"
        else:
            new_diff_pct = row_data.actual_percent - new_target
            new_diff_amt = new_diff_pct / _D100 * self._allocation_data.total_value
            diff_text = _colored_diff(new_diff_pct, new_diff_amt)
        row_widget = target_input.parent
        if isinstance(row_widget, _AllocationRow):
            row_widget.update_diff(diff_text)

    def _update_warning(self) -> None:
        """Show or hide the over-100% warning banner."""
        total = self._current_target_sum()
        warning = self.query_one("#gav-warning", Static)
        if total > _D100:
            warning.update(f"[!] Total target is {total.normalize():f}% — must not exceed 100%.")
            warning.add_class("visible")
        else:
            warning.update("")
            warning.remove_class("visible")

    # ── Async workers ─────────────────────────────────────────────────────────

    async def _load_goals(self) -> None:
        """Fetch the goal list and load the initial goal's allocation data."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            items: list[GoalListItem] = self.app.services.goals.get_goals_for_allocation_view(as_of)  # type: ignore[attr-defined]
            self._goal_items = items

            if not items:
                self.query_one("#gav-left", _GoalListPane).update([], 0)
                await self._show_empty("No goals found.")
                return

            if self._initial_goal_id is not None:
                for i, item in enumerate(items):
                    if item.goal_id == self._initial_goal_id:
                        self._selected_idx = i
                        break

            self.query_one("#gav-left", _GoalListPane).update(items, self._selected_idx)
            await self._load_allocation_data(items[self._selected_idx].goal_id, focus_first=True)

        except Exception as exc:
            logger.error("load_goals_failed", error=str(exc), exc_info=True)
            await self._show_empty(f"Error: {exc}")

    async def _load_allocation_data(self, goal_id: int, *, focus_first: bool = False) -> None:
        """Load and render the right pane for the given goal."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        rows_container = self.query_one("#gav-rows", VerticalScroll)
        await rows_container.remove_children()
        await rows_container.mount(LoadingIndicator())

        try:
            data: GoalAllocationData = (
                await self.app.services.goals.get_goal_allocation_data(goal_id, as_of)  # type: ignore[attr-defined]
            )
            self._allocation_data = data
            self._persisted_targets = {row.asset_class_id: row.target_percent for row in data.rows}
            self._actual_amt_total = data.total_value
            self._dirty = False
            self.refresh_bindings()

            self.query_one("#gav-right-header", Static).update(
                f"{data.goal_name} — Asset Allocation"
            )

            await rows_container.remove_children()
            if data.rows:
                new_rows = [
                    _AllocationRow(
                        asset_class_id=row.asset_class_id,
                        asset_class_name=row.asset_class_name,
                        target_initial=PercentInput.format(row.target_percent),
                        actual_pct_text=_fmt_actual_pct(row.actual_percent),
                        actual_amt_text=_fmt_amt(row.actual_percent / _D100 * data.total_value),
                        diff_text=(
                            "—"
                            if row.target_percent == _D0
                            else _colored_diff(row.difference_percent, row.difference_amount)
                        ),
                    )
                    for row in data.rows
                ]
                await rows_container.mount(*new_rows)
                if focus_first:
                    self._focus_first_target_input()

            self._update_warning()
            self._update_totals()

        except Exception as exc:
            logger.error("load_allocation_failed", error=str(exc), exc_info=True)
            await rows_container.remove_children()
            await rows_container.mount(Static(f"Error loading allocation: {exc}"))

    async def _show_empty(self, message: str) -> None:
        """Display a placeholder in the right pane."""
        rows_container = self.query_one("#gav-rows", VerticalScroll)
        await rows_container.remove_children()
        await rows_container.mount(Static(message))
        self.query_one("#gav-right-header", Static).update("")

    async def _do_save_targets(self) -> None:
        """Read current inputs and persist via G-OP-8."""
        if self._allocation_data is None:
            return
        as_of = self.app.effective_date  # type: ignore[attr-defined]

        targets: list[tuple[int, Decimal]] = []
        for row in self._allocation_data.rows:
            try:
                widget = self.query_one(f"#target-{row.asset_class_id}", PercentInput)
                pct = PercentInput.parse(widget.value)
            except (InvalidOperation, Exception):
                pct = _D0
            targets.append((row.asset_class_id, pct))

        try:
            self.app.services.goals.update_goal_asset_class_targets(  # type: ignore[attr-defined]
                self._allocation_data.goal_id, targets, as_of
            )
            self._persisted_targets = dict(targets)
            self._dirty = False
            self.refresh_bindings()
            self._update_warning()

            # Refresh left-pane [!] indicators after targets may have changed.
            goals_service = self.app.services.goals  # type: ignore[attr-defined]
            updated: list[GoalListItem] = goals_service.get_goals_for_allocation_view(as_of)
            self._goal_items = updated
            self.query_one("#gav-left", _GoalListPane).update(updated, self._selected_idx)

            self.notify("Allocation saved.", timeout=2)

        except Exception as exc:
            logger.error("save_targets_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save: {exc}", severity="error", timeout=5)
