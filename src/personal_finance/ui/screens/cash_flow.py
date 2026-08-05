"""Cash Flow screens — Flows F-12, F-13, F-14, F-15.

This module contains the three sibling views of the Cash Flow module plus the
AutomatedContributionDialog modal. All three views share a 33/67 split layout
via :class:`~personal_finance.ui.screens.base.TwoPaneScreen`.

Left-pane navigation covers all three views:
  - Person items    → :class:`CashFlowPersonProfileView` (F-12) with that person active
  - Expenses        → :class:`CashFlowExpensesView` (F-13)
  - Household CF    → :class:`HouseholdCashFlowReportView` (F-14)

``Esc`` in any view returns directly to the Dashboard; it is not a "back" here.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import ClassVar

import structlog
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.events import Key
from textual.widget import Widget
from textual.widgets import Input, Static

from personal_finance.service.application.cash_flow_app_service import (
    GoalOption,
    PersonNavItem,
    PersonProfileFormData,
)
from personal_finance.ui.palette import ACCENT_CYAN, TEXT_DIM
from personal_finance.ui.screens.base import LeftNavPane, TwoPaneScreen
from personal_finance.ui.widgets.inputs import AppSelect, MoneyInput

logger = structlog.get_logger(__name__)

_D0 = Decimal("0")

# ── Nav item model ─────────────────────────────────────────────────────────────


class _NavKind(enum.Enum):
    PERSON = "person"
    EXPENSES = "expenses"
    REPORT = "report"


@dataclass
class _NavEntry:
    """One selectable item in the cash flow left-nav pane."""

    kind: _NavKind
    label: str
    profile_id: int | None = None


_NAV_EXPENSES = _NavEntry(kind=_NavKind.EXPENSES, label="Expenses")
_NAV_REPORT = _NavEntry(kind=_NavKind.REPORT, label="Household Cash Flow")


# ── Left-pane navigation widget ────────────────────────────────────────────────


class _CashFlowNavPane(LeftNavPane):
    """Left pane: person profile items + Expenses + Household Cash Flow.

    Up/Down navigation is handled by the owning screen via ``on_key``.
    Mouse clicks are handled by the
    :class:`~personal_finance.ui.screens.base.LeftNavPane` base via
    ``on_select``.
    """

    def __init__(
        self,
        id: str | None = None,
        on_select: Callable[[int], None] | None = None,
    ) -> None:
        """Initialise with an empty item list."""
        super().__init__(id=id, on_select=on_select)
        self._items: list[_NavEntry] = []
        self._n_persons: int = 0

    def update(
        self,
        items: list[_NavEntry],
        selected_idx: int,
        n_persons: int,
    ) -> None:
        """Replace the nav items and trigger a repaint.

        Args:
            items: All selectable items (persons + Expenses + Household CF).
            selected_idx: Index of the currently highlighted item.
            n_persons: Number of person items at the start of the list (used to
                place the separator between persons and nav items).
        """
        self._items = items
        self._selected_idx = selected_idx
        self._n_persons = n_persons
        self.refresh()

    def render(self) -> Text:
        """Build the Rich Text renderable for the nav list."""
        text = Text()
        text.append("Profiles\n", style=f"{TEXT_DIM} bold")

        for i, item in enumerate(self._items):
            if i == self._n_persons and self._n_persons > 0:
                text.append(" " + "─" * 16 + "\n", style=ACCENT_CYAN)

            cursor = ">" if i == self._selected_idx else " "
            style = "bold white" if i == self._selected_idx else TEXT_DIM
            line = f"{cursor} {item.label}"
            text.append(line, style=style)
            if i < len(self._items) - 1:
                text.append("\n")

        return text

    def _y_to_item_idx(self, y: int) -> int | None:
        """Convert a widget-relative y coordinate to an item list index.

        Accounts for top padding (1 row) and the "Profiles" header line.
        Returns ``None`` for padding, the header, and separator rows.
        """
        content_line = y - 1  # subtract top padding
        if content_line <= 0:
            return None

        # Lines 1..n_persons are person items (0-indexed)
        if content_line <= self._n_persons:
            idx = content_line - 1
            return idx if idx < len(self._items) else None

        # The next line is the separator when persons exist
        separator_lines = 1 if self._n_persons > 0 else 0
        nav_start = self._n_persons + separator_lines + 1
        if content_line >= nav_start:
            idx = self._n_persons + (content_line - nav_start)
            return idx if idx < len(self._items) else None

        return None


# ── Profile form field row ─────────────────────────────────────────────────────


class _ProfileFieldRow(Widget):
    """One labeled numeric input row in the person profile form."""

    DEFAULT_CSS = """
    _ProfileFieldRow {
        layout: horizontal;
        height: 3;
        padding: 0 1;
    }
    _ProfileFieldRow .pfr-label {
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    _ProfileFieldRow .pfr-input {
        width: 20;
        height: 3;
    }
    """

    def __init__(
        self, label: str, field_id: str, value: str = "0.00", disabled: bool = False
    ) -> None:
        """Initialise with a label, field DOM ID, initial value, and disabled state."""
        super().__init__()
        self._label = label
        self._field_id = field_id
        self._value = value
        self._disabled = disabled

    def compose(self) -> ComposeResult:
        """Render the label + right-aligned numeric input."""
        yield Static(self._label, classes="pfr-label")
        yield MoneyInput(
            value=self._value,
            id=self._field_id,
            classes="pfr-input",
            disabled=self._disabled,
        )


class _ProfileGoalRow(Widget):
    """Label + Select dropdown row for the RRSP goal field."""

    DEFAULT_CSS = """
    _ProfileGoalRow {
        layout: horizontal;
        height: 3;
        padding: 0 1;
    }
    _ProfileGoalRow .pfr-label {
        width: 1fr;
        content-align: left middle;
        color: #aaaaaa;
    }
    _ProfileGoalRow .pfr-select {
        width: 20;
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        """Render the label + Select dropdown."""
        yield Static("Auto RRSP and Match Goal", classes="pfr-label")
        yield AppSelect(
            [],
            id="cfp-rrsp-goal",
            classes="pfr-select",
            allow_blank=True,
        )


# ── CashFlowPersonProfileView (F-12) ──────────────────────────────────────────


class CashFlowPersonProfileView(TwoPaneScreen):
    """Cash Flow Person Profile View — Flow F-12.

    Left pane: person list + separator + Expenses / Household Cash Flow nav items.
    Right pane: editable income and RRSP fields for the selected person.

    Navigating to Expenses or Household Cash Flow immediately switches screens.
    Inline-persist: pressing Enter on any field saves the full profile (CF-OP-2).
    ``Esc`` returns directly to the Dashboard.
    """

    SCREEN_TITLE = "Cash Flow"
    _CONTEXTUAL_ACTIONS: ClassVar[frozenset[str]] = frozenset()

    BINDINGS = [
        Binding("escape", "go_to_dashboard", "Back to Dashboard", show=True),
    ]

    DEFAULT_CSS = f"""
    CashFlowPersonProfileView #tps-right {{
        padding: 0 1;
        overflow-y: auto;
    }}

    #cfp-right-header {{
        height: 1;
        margin: 1 1 1 1;
        color: #aaaaff;
        text-style: bold;
    }}

    #cfp-form {{
        height: auto;
        margin: 1 0;
    }}

    #cfp-separator-1, #cfp-separator-2 {{
        height: 1;
        margin: 0 1;
        color: {ACCENT_CYAN};
    }}

    #cfp-no-person {{
        padding: 1 2;
        color: {TEXT_DIM};
        display: none;
    }}

    #cfp-no-person.visible {{
        display: block;
    }}
    """

    def __init__(self, initial_profile_id: int | None = None) -> None:
        """Initialise screen state.

        Args:
            initial_profile_id: Profile to pre-select; defaults to the first person.
        """
        super().__init__()
        self._initial_profile_id = initial_profile_id
        self._nav_items: list[_NavEntry] = []
        self._n_persons: int = 0
        self._selected_idx: int = 0
        self._current_profile: PersonProfileFormData | None = None
        self._goal_options: list[GoalOption] = []
        self._loading: bool = False

    # ── Composition ───────────────────────────────────────────────────────────

    def _compose_left_pane(self) -> ComposeResult:
        """Yield the nav pane."""
        yield _CashFlowNavPane(id="tps-left", on_select=self._navigate_to)

    def _compose_right_pane(self) -> ComposeResult:
        """Yield the profile form pane."""
        with VerticalScroll(id="tps-right", can_focus=False):
            yield Static("", id="cfp-right-header")
            yield Static("Select a person to view their profile.", id="cfp-no-person")
            with Widget(id="cfp-form"):
                yield _ProfileFieldRow("Gross income", "cfp-gross-income")
                yield _ProfileFieldRow("Net income", "cfp-net-income")
                yield Static("─" * 30, id="cfp-separator-1")
                yield _ProfileFieldRow("Gross bonus", "cfp-gross-bonus")
                yield _ProfileFieldRow("Net bonus", "cfp-net-bonus")
                yield Static("─" * 30, id="cfp-separator-2")
                yield _ProfileGoalRow()
                yield _ProfileFieldRow("Auto RRSP contribution", "cfp-rrsp-deducted", disabled=True)
                yield _ProfileFieldRow("Auto RRSP match", "cfp-rrsp-matched", disabled=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Set effective date, register watchers, and kick off data loading."""
        super().on_mount()
        goal_select = self.query_one("#cfp-rrsp-goal", AppSelect)
        self.watch(goal_select, "expanded", self._on_goal_expanded_changed, init=False)
        self.run_worker(self._load_nav_and_profile(), exclusive=True, name="cfp-load")

    # ── Keyboard handling ─────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        """Navigate the nav pane when it has focus."""
        if not isinstance(self.focused, _CashFlowNavPane):
            return
        if event.key == "down":
            event.stop()
            if self._nav_items:
                new_idx = min(self._selected_idx + 1, len(self._nav_items) - 1)
                if new_idx != self._selected_idx:
                    self._navigate_to(new_idx)
        elif event.key == "up":
            event.stop()
            if self._nav_items:
                new_idx = max(self._selected_idx - 1, 0)
                if new_idx != self._selected_idx:
                    self._navigate_to(new_idx)
        elif event.key == "enter":
            event.stop()
            if self._nav_items and self._nav_items[self._selected_idx].kind == _NavKind.PERSON:
                self._focus_first_form_input()

    # ── Reactive watchers ─────────────────────────────────────────────────────

    def _on_goal_expanded_changed(self, old_expanded: bool, new_expanded: bool) -> None:
        """Focus the contribution input when the goal dropdown closes with a selection."""
        if not old_expanded or new_expanded or self._loading:
            return
        goal_select = self.query_one("#cfp-rrsp-goal", AppSelect)
        if goal_select.value is AppSelect.NULL:
            return
        deducted_input = self.query_one("#cfp-rrsp-deducted", MoneyInput)
        if not deducted_input.disabled:
            deducted_input.focus()

    # ── Input / Select change handlers ────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Save the full profile when Enter is pressed on any form input."""
        if self._loading or self._current_profile is None:
            return
        if not (event.input.id or "").startswith("cfp-"):
            return
        self._save_profile()

    def on_select_changed(self, event: AppSelect.Changed) -> None:
        """React to the RRSP goal dropdown changing.

        Selecting a goal enables Auto RRSP contribution and moves focus there.
        Clearing the goal zeroes and disables both RRSP inputs, then saves.
        """
        if self._loading or self._current_profile is None:
            return
        if event.select.id != "cfp-rrsp-goal":
            return

        deducted_input = self.query_one("#cfp-rrsp-deducted", MoneyInput)
        matched_input = self.query_one("#cfp-rrsp-matched", MoneyInput)

        if event.value is not AppSelect.NULL:
            deducted_input.disabled = False
        else:
            deducted_input.value = MoneyInput.format(_D0)
            deducted_input.disabled = True
            matched_input.value = MoneyInput.format(_D0)
            matched_input.disabled = True

        self._save_profile()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Enable Auto RRSP match once the user enters a positive contribution.

        Gated on ``has_focus`` so only genuine user typing reacts. Value changes
        from profile loading or from widget construction (``Input.__init__`` posts
        a ``Changed`` for its initial value) fire on an *unfocused* input; without
        this guard a stale construction-time event processed after the first load
        would zero out the match field. Focus is the reliable "the user did this"
        signal — timing flags like ``_loading`` cannot catch a queued event that
        is processed after loading completes.
        """
        if event.input.id != "cfp-rrsp-deducted" or not event.input.has_focus:
            return
        matched_input = self.query_one("#cfp-rrsp-matched", MoneyInput)
        try:
            amount = MoneyInput.parse(event.value)
        except InvalidOperation:
            return
        if amount <= _D0:
            matched_input.value = MoneyInput.format(_D0)
            matched_input.disabled = True
        else:
            matched_input.disabled = False

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_go_to_dashboard(self) -> None:
        """Return directly to the Dashboard (Esc)."""
        from personal_finance.ui.screens.dashboard import DashboardScreen  # noqa: PLC0415

        self.app.switch_screen(DashboardScreen())

    # ── Navigation helpers ────────────────────────────────────────────────────

    def _navigate_to(self, new_idx: int) -> None:
        """Handle left-pane navigation to a new item index."""
        entry = self._nav_items[new_idx]
        self._selected_idx = new_idx
        self.query_one("#tps-left", _CashFlowNavPane).update(
            self._nav_items, self._selected_idx, self._n_persons
        )

        if entry.kind == _NavKind.PERSON:
            assert entry.profile_id is not None
            self.run_worker(
                self._load_profile(entry.profile_id),
                exclusive=True,
                name="cfp-load-profile",
            )
        elif entry.kind == _NavKind.EXPENSES:
            from personal_finance.ui.screens.cash_flow_expenses import (  # noqa: PLC0415
                CashFlowExpensesView,
            )

            self.app.switch_screen(CashFlowExpensesView())
        elif entry.kind == _NavKind.REPORT:
            from personal_finance.ui.screens.cash_flow_report import (  # noqa: PLC0415
                HouseholdCashFlowReportView,
            )

            self.app.switch_screen(HouseholdCashFlowReportView())

    def _focus_first_form_input(self) -> None:
        """Move focus to the Gross income input."""
        try:
            self.query_one("#cfp-gross-income", Input).focus()
        except Exception:
            pass

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_profile(self) -> None:
        """Read all form inputs and persist via CF-OP-2."""
        if self._current_profile is None:
            return
        try:
            gross = MoneyInput.parse(self.query_one("#cfp-gross-income", MoneyInput).value)
            net = MoneyInput.parse(self.query_one("#cfp-net-income", MoneyInput).value)
            gross_bonus = MoneyInput.parse(self.query_one("#cfp-gross-bonus", MoneyInput).value)
            net_bonus = MoneyInput.parse(self.query_one("#cfp-net-bonus", MoneyInput).value)
            rrsp_deducted = MoneyInput.parse(self.query_one("#cfp-rrsp-deducted", MoneyInput).value)
            rrsp_matched = MoneyInput.parse(self.query_one("#cfp-rrsp-matched", MoneyInput).value)

            goal_select = self.query_one("#cfp-rrsp-goal", AppSelect)
            raw_goal = goal_select.value
            goal_id: int | None = int(raw_goal) if raw_goal is not AppSelect.NULL else None  # type: ignore[arg-type]

            as_of = self.app.effective_date  # type: ignore[attr-defined]
            self.app.services.cash_flow.update_person_profile(  # type: ignore[attr-defined]
                profile_id=self._current_profile.profile_id,
                effective_date=as_of,
                gross_annual_income=gross,
                net_annual_income=net,
                gross_bonus=gross_bonus,
                net_bonus=net_bonus,
                auto_rrsp_deducted=rrsp_deducted,
                rrsp_matched=rrsp_matched,
                auto_rrsp_goal_id=goal_id,
            )
        except (InvalidOperation, ValueError) as exc:
            self.notify(str(exc), severity="error", timeout=4)

    # ── Async workers ─────────────────────────────────────────────────────────

    async def _load_nav_and_profile(self) -> None:
        """Build the nav pane and load the initial person's profile."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            person_items: list[PersonNavItem] = self.app.services.cash_flow.get_person_nav_items()  # type: ignore[attr-defined]
            self._goal_options = self.app.services.cash_flow.get_goal_options(as_of)  # type: ignore[attr-defined]

            self._n_persons = len(person_items)
            self._nav_items = [
                _NavEntry(
                    kind=_NavKind.PERSON,
                    label=item.person_name,
                    profile_id=item.profile_id,
                )
                for item in person_items
            ] + [_NAV_EXPENSES, _NAV_REPORT]

            # Resolve initial selection
            self._selected_idx = 0
            if self._initial_profile_id is not None:
                for i, item in enumerate(self._nav_items):
                    if item.profile_id == self._initial_profile_id:
                        self._selected_idx = i
                        break

            self.query_one("#tps-left", _CashFlowNavPane).update(
                self._nav_items, self._selected_idx, self._n_persons
            )

            if person_items:
                first_profile_id = self._nav_items[self._selected_idx].profile_id
                if first_profile_id is not None:
                    await self._load_profile(first_profile_id)

        except Exception as exc:
            logger.error("cfp_load_nav_failed", error=str(exc), exc_info=True)
            self.notify(f"Error loading profiles: {exc}", severity="error", timeout=5)

    async def _load_profile(self, profile_id: int) -> None:
        """Load and render the right pane for the given profile."""
        self._loading = True
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            data: PersonProfileFormData = self.app.services.cash_flow.get_person_profile_form_data(  # type: ignore[attr-defined]
                profile_id, as_of
            )
            self._current_profile = data

            self.query_one("#cfp-right-header", Static).update(f"{data.person_name} Profile")

            has_goal = data.auto_rrsp_goal_id is not None
            has_contribution = data.auto_rrsp_deducted > _D0

            goal_select = self.query_one("#cfp-rrsp-goal", AppSelect)
            deducted_input = self.query_one("#cfp-rrsp-deducted", MoneyInput)
            matched_input = self.query_one("#cfp-rrsp-matched", MoneyInput)

            with self.prevent(AppSelect.Changed, Input.Changed):
                self.query_one("#cfp-gross-income", MoneyInput).value = MoneyInput.format(
                    data.gross_annual_income
                )
                self.query_one("#cfp-net-income", MoneyInput).value = MoneyInput.format(
                    data.net_annual_income
                )
                self.query_one("#cfp-gross-bonus", MoneyInput).value = MoneyInput.format(
                    data.gross_bonus
                )
                self.query_one("#cfp-net-bonus", MoneyInput).value = MoneyInput.format(
                    data.net_bonus
                )

                goal_select.set_options([(opt.name, opt.goal_id) for opt in self._goal_options])
                goal_select.value = (
                    data.auto_rrsp_goal_id if data.auto_rrsp_goal_id is not None else AppSelect.NULL
                )

                deducted_input.value = (
                    MoneyInput.format(data.auto_rrsp_deducted)
                    if has_goal
                    else MoneyInput.format(_D0)
                )
                matched_input.value = (
                    MoneyInput.format(data.rrsp_matched)
                    if (has_goal and has_contribution)
                    else MoneyInput.format(_D0)
                )
                deducted_input.disabled = not has_goal
                matched_input.disabled = not (has_goal and has_contribution)

            self.query_one("#cfp-no-person", Static).remove_class("visible")

        except Exception as exc:
            logger.error("cfp_load_profile_failed", error=str(exc), exc_info=True)
            self.notify(f"Error loading profile: {exc}", severity="error", timeout=5)
        finally:
            self._loading = False
