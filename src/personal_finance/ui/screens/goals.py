"""Goals List screen — Flow F-8.

Displays all active goals in an editable grid:
  - Name: editable text input (inline G-OP-3 name update).
  - Goal amount: F6OpenableField — editable for Manual goals, gold-bordered
    read-only for PV/NoTarget goals. F6 → GoalValueDialog (F-9b).
  - Investment Allocation: gold-bordered read-only; F6 → SelectAccountsDialog
    (F-10, stub).
  - Bank Allocation: F6OpenableField — editable for Scalar strategy, gold-
    bordered read-only for AutoFill. F6 → BankAccountAllocationDialog (F-11, stub).
  - Difference: read-only calculated value.

Footer actions:
  F2 → CreateGoalDialog (F-9a)
  F6 → open focused dialog (contextual)
  F8 → discard focused goal (G-OP-4)
  F3 → Allocation View (F-11b, stub)
  Esc → Dashboard
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import structlog
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.events import Key
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Input, LoadingIndicator, Static

from personal_finance.service.application.goal_app_service import (
    GoalsSummary,
)
from personal_finance.service.application.goal_app_service import (
    GoalSummaryRow as GoalRowData,
)
from personal_finance.ui.palette import PANEL_FILL
from personal_finance.ui.screens.dialogs import ConfirmationDialog
from personal_finance.ui.screens.goal_dialogs import (
    BankAccountAllocationDialog,
    CreateGoalDialog,
    GoalValueDialog,
    SelectAccountsDialog,
)
from personal_finance.ui.widgets.inputs import (
    F6OpenableField,
    GoldBorderDisplay,
    MoneyInput,
    TextInput,
)
from personal_finance.ui.widgets.split_footer import SplitFooter

logger = structlog.get_logger(__name__)


# ── Formatting helpers ─────────────────────────────────────────────────────────


def _fmt_diff(value: Decimal | None) -> str:
    """Format the Difference column with Rich color; return ``N/A`` for no-target goals.

    Positive (over-funded) → green. Negative (under-funded) → red.
    """
    if value is None:
        return "N/A"
    text = MoneyInput.format(value)
    if value > Decimal("0"):
        return f"[green]{text}[/]"
    if value < Decimal("0"):
        return f"[red]{text}[/]"
    return text


# ── GoalRow ────────────────────────────────────────────────────────────────────


class GoalRow(Widget):
    """One row in the Goals list grid.

    Posts typed messages upward to the owning screen for name and value edits.
    """

    DEFAULT_CSS = """
    GoalRow {
        layout: horizontal;
        height: 3;
        padding: 0 2;
    }
    GoalRow .gr-name {
        width: 1fr;
        min-width: 14;
        height: 3;
    }
    GoalRow .gr-goal {
        width: 20;
        height: 3;
        margin-left: 1;
    }
    GoalRow .gr-goal-empty GoldBorderDisplay {
        content-align: center middle;
    }
    GoalRow .gr-inv-alloc {
        width: 16;
        height: 3;
        margin-left: 1;
    }
    GoalRow .gr-bank {
        width: 20;
        height: 3;
        margin-left: 1;
    }
    GoalRow .gr-diff {
        width: 14;
        height: 3;
        margin-left: 1;
        content-align: right middle;
        color: #aaaaaa;
    }
    """

    class NameSubmitted(Message):
        """User submitted a modified goal name.

        Attributes:
            goal_id: Primary key of the goal.
            new_name: Updated display name.
        """

        def __init__(self, goal_id: int, new_name: str) -> None:
            """Store fields."""
            super().__init__()
            self.goal_id = goal_id
            self.new_name = new_name

    class GoalAmountSubmitted(Message):
        """User submitted a new scalar goal target (Manual goals only).

        Attributes:
            goal_id: Primary key of the goal.
            raw_value: Raw Input string (unparsed).
        """

        def __init__(self, goal_id: int, raw_value: str) -> None:
            """Store fields."""
            super().__init__()
            self.goal_id = goal_id
            self.raw_value = raw_value

    class BankAllocSubmitted(Message):
        """User submitted a new scalar bank-claim amount.

        Attributes:
            goal_id: Primary key of the goal.
            raw_value: Raw Input string (unparsed).
        """

        def __init__(self, goal_id: int, raw_value: str) -> None:
            """Store fields."""
            super().__init__()
            self.goal_id = goal_id
            self.raw_value = raw_value

    def __init__(self, row: GoalRowData) -> None:
        """Store the row data and initialise mutable display state."""
        super().__init__(id=f"gr-{row.goal_id}")
        self._row = row
        self._original_name: str = row.name
        self._current_goal_target: Decimal | None = row.goal_target
        self._current_inv_alloc: Decimal = row.investment_allocation
        self._current_bank_alloc: Decimal = row.bank_allocation

    @property
    def goal_id(self) -> int:
        """Primary key of the goal this row represents."""
        return self._row.goal_id

    @property
    def is_autofill_bank(self) -> bool:
        """True when this goal uses the AutoFill bank-portion strategy."""
        return self._row.is_autofill

    @property
    def current_goal_target(self) -> Decimal | None:
        """Current goal target amount, updated after inline edits."""
        return self._current_goal_target

    @property
    def current_bank_alloc(self) -> Decimal:
        """Current bank-claim amount, updated after inline edits."""
        return self._current_bank_alloc

    def compose(self) -> ComposeResult:
        """Render name, goal amount, investment alloc, bank alloc, difference cells."""
        gid = self._row.goal_id
        is_manual = self._row.goal_type == "manual"
        is_scalar_bank = not self._row.is_autofill

        # Goal amount display value
        if self._row.goal_type == "none":
            goal_display = "  - No goal -"
        else:
            goal_display = MoneyInput.format(self._row.goal_target, placeholder="")

        # Bank alloc display value
        bank_display = MoneyInput.format(self._row.bank_allocation)

        yield TextInput(
            value=self._row.name,
            id=f"goal-name-{gid}",
            classes="gr-name",
        )
        goal_classes = "gr-goal gr-goal-empty" if self._row.goal_type == "none" else "gr-goal"
        yield F6OpenableField(
            goal_display,
            editable=is_manual,
            id=f"goal-amount-{gid}",
            classes=goal_classes,
        )
        yield GoldBorderDisplay(
            MoneyInput.format(self._row.investment_allocation),
            id=f"inv-alloc-{gid}",
            classes="gr-inv-alloc",
        )
        yield F6OpenableField(
            bank_display,
            editable=is_scalar_bank,
            id=f"bank-alloc-{gid}",
            classes="gr-bank",
        )
        yield Static(_fmt_diff(self._row.difference), classes="gr-diff")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle submission for all inputs in this row.

        Inputs inside F6OpenableField bubble their Input.Submitted past the
        container (which has can_focus=False) up to this row handler; we
        identify them by checking the parent widget.

        - Name field: post message only if value changed; advance focus.
        - Numeric fields (F6OpenableField): post message unconditionally (the
          screen handler does change detection after parsing). Focus advancement
          is handled by RightAlignedNumericInput.on_input_submitted (fires
          before this handler), so this branch must NOT also call focus_next().
        """
        event.stop()
        gid = self._row.goal_id
        input_id = event.input.id or ""
        parent = event.input.parent

        if input_id == f"goal-name-{gid}":
            if event.value != self._original_name:
                self.post_message(self.NameSubmitted(gid, event.value))
            # TextInput already advanced focus; do not call focus_next() again.
        elif isinstance(parent, F6OpenableField):
            f6_id = (parent.id or "") if parent.id else ""
            if f6_id == f"goal-amount-{gid}":
                self.post_message(self.GoalAmountSubmitted(gid, event.value))
            elif f6_id == f"bank-alloc-{gid}":
                self.post_message(self.BankAllocSubmitted(gid, event.value))

    def update_goal_target(self, new_target: Decimal) -> None:
        """Update cached state and refresh in-place after a goal-target save.

        For AutoFill goals the bank-claim display is also updated because it
        is derived directly from ``new_target - investment_allocation``.
        """
        self._current_goal_target = new_target
        if self._row.is_autofill:
            new_bank = new_target - self._current_inv_alloc
            self._current_bank_alloc = new_bank
            try:
                self.query_one(f"#bank-alloc-{self._row.goal_id}", F6OpenableField).set_state(
                    editable=False, value=MoneyInput.format(new_bank)
                )
            except Exception:
                pass
        self._refresh_difference()

    def update_bank_alloc(self, new_amount: Decimal) -> None:
        """Update cached state and refresh in-place after a bank-claim save."""
        self._current_bank_alloc = new_amount
        self._refresh_difference()

    def _refresh_difference(self) -> None:
        if self._row.goal_type == "none" or self._current_goal_target is None:
            return
        diff = self._current_inv_alloc + self._current_bank_alloc - self._current_goal_target
        try:
            self.query_one(".gr-diff", Static).update(_fmt_diff(diff))
        except Exception:
            pass


# ── _ColumnHeaders ─────────────────────────────────────────────────────────────


class _ColumnHeaders(Horizontal):
    """Column header row for the goals grid."""

    DEFAULT_CSS = """
    _ColumnHeaders {
        height: 1;
        padding: 0 2;
        margin-top: 1;
    }
    _ColumnHeaders .ch-name {
        width: 1fr;
        min-width: 14;
        color: #ffffff;
        text-style: bold;
    }
    _ColumnHeaders .ch-goal {
        width: 20;
        margin-left: 1;
        color: #ffffff;
        text-style: bold;
    }
    _ColumnHeaders .ch-inv {
        width: 16;
        margin-left: 1;
        color: #ffffff;
        text-style: bold;
    }
    _ColumnHeaders .ch-bank {
        width: 20;
        margin-left: 1;
        color: #ffffff;
        text-style: bold;
    }
    _ColumnHeaders .ch-diff {
        width: 14;
        margin-left: 1;
        color: #ffffff;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        """Render column header labels."""
        yield Static("Name", classes="ch-name")
        yield Static("Goal", classes="ch-goal")
        yield Static("Inv. Alloc", classes="ch-inv")
        yield Static("Bank Alloc", classes="ch-bank")
        yield Static("Difference", classes="ch-diff")


# ── GoalsListScreen ────────────────────────────────────────────────────────────


class GoalsListScreen(Screen[None]):
    """Goals List screen — Flow F-8."""

    def __init__(self, initial_goal_id: int | None = None) -> None:
        """Initialise screen-level cached values used for incremental overclaim updates.

        Args:
            initial_goal_id: When returning from GoalAllocationView (F-11b), the
                goal that was selected there is passed here so its row can be
                pre-focused after the screen loads.
        """
        super().__init__()
        self._initial_goal_id = initial_goal_id
        self._total_bank_claims: Decimal = Decimal("0")
        self._bank_balance: Decimal = Decimal("0")

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("f2", "create_goal", "New Goal", show=True),
        Binding("f3", "allocation_view", "Allocation View", show=True),
        Binding("f6", "open_focused", "Open", show=True),
        Binding("f8", "discard_goal", "Discard Goal", show=True),
    ]

    DEFAULT_CSS = f"""
    GoalsListScreen {{
        background: #000080;
    }}

    #gl-title-bar {{
        background: {PANEL_FILL};
        height: 3;
        border-bottom: solid #aaaaff;
        padding: 0 2;
    }}

    #gl-title {{
        color: #aaaaff;
        text-style: bold;
        width: 1fr;
        height: 3;
        content-align: left middle;
    }}

    #gl-date {{
        color: #aaaaaa;
        height: 3;
        content-align: right middle;
        width: 14;
    }}

    #gl-content {{
        background: #000080;
        padding: 0 0 1 0;
    }}

    #gl-overclaim {{
        height: 1;
        color: #ff4444;
        padding: 0 2;
        margin-bottom: 1;
        content-align: right middle;
        display: none;
    }}

    #gl-overclaim.visible {{
        display: block;
    }}
    """

    def compose(self) -> ComposeResult:
        """Render the title bar, column headers, scrollable goal rows, and footer."""
        with Horizontal(id="gl-title-bar"):
            yield Static("Goals", id="gl-title")
            yield Static("", id="gl-date")
        yield _ColumnHeaders()
        with VerticalScroll(id="gl-content", can_focus=False):
            yield LoadingIndicator()
        yield Static("", id="gl-overclaim")
        yield SplitFooter({"open_focused", "discard_goal"})

    def on_mount(self) -> None:
        """Show the effective date and kick off the data-load worker."""
        self.query_one("#gl-date", Static).update(
            str(self.app.effective_date)  # type: ignore[attr-defined]
        )
        focus_id = (
            f"goal-name-{self._initial_goal_id}" if self._initial_goal_id is not None else None
        )
        self.run_worker(
            self._load_data(focus_widget_id=focus_id), exclusive=True, name="load-goals"
        )

    def on_key(self, event: Key) -> None:
        """Up/Down navigate between focusable widgets."""
        if event.key == "down":
            self.focus_next()
            event.stop()
        elif event.key == "up":
            self.focus_previous()
            event.stop()

    def on_descendant_focus(self) -> None:
        """Refresh footer bindings when focus changes."""
        self.refresh_bindings()

    def on_descendant_blur(self) -> None:
        """Refresh footer bindings when focus changes."""
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Show contextual bindings only when appropriate."""
        if action == "open_focused":
            return self._f6_context() is not None
        if action == "discard_goal":
            return self._focused_goal_id() is not None
        return True

    # ── Messages from GoalRow ──────────────────────────────────────────────────

    def on_goal_row_name_submitted(self, event: GoalRow.NameSubmitted) -> None:
        """Persist an inline goal name edit."""
        name = event.new_name.strip()
        if not name:
            self.notify("Name cannot be empty.", severity="error", timeout=3)
            return
        self.run_worker(
            self._do_update_name(event.goal_id, name),
            exclusive=False,
            name=f"update-goal-name-{event.goal_id}",
        )

    def on_goal_row_goal_amount_submitted(self, event: GoalRow.GoalAmountSubmitted) -> None:
        """Persist an inline Manual goal target edit if the value changed."""
        try:
            new_value = MoneyInput.parse(event.raw_value)
        except InvalidOperation:
            self.notify("Invalid amount — enter a numeric value.", severity="error", timeout=4)
            return
        try:
            if self.query_one(f"#gr-{event.goal_id}", GoalRow).current_goal_target == new_value:
                return
        except Exception:
            pass
        self.run_worker(
            self._do_update_goal_scalar(event.goal_id, new_value),
            exclusive=False,
            name=f"update-goal-scalar-{event.goal_id}",
        )

    def on_goal_row_bank_alloc_submitted(self, event: GoalRow.BankAllocSubmitted) -> None:
        """Persist an inline Scalar bank-claim edit if the value changed."""
        try:
            new_amount = MoneyInput.parse(event.raw_value)
        except InvalidOperation:
            self.notify("Invalid amount — enter a numeric value.", severity="error", timeout=4)
            return
        try:
            if self.query_one(f"#gr-{event.goal_id}", GoalRow).current_bank_alloc == new_amount:
                return
        except Exception:
            pass
        self.run_worker(
            self._do_update_bank_scalar(event.goal_id, new_amount),
            exclusive=False,
            name=f"update-bank-scalar-{event.goal_id}",
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_go_back(self) -> None:
        """Return to Dashboard (Esc)."""
        self.app.pop_screen()

    def action_create_goal(self) -> None:
        """Open CreateGoalDialog (F2 — F-9a)."""
        effective_date = self.app.effective_date  # type: ignore[attr-defined]

        def _on_dismiss(new_id: int | None) -> None:
            if new_id is not None:
                self.run_worker(self._load_data(), exclusive=True, name="load-goals")

        self.app.push_screen(CreateGoalDialog(effective_date), callback=_on_dismiss)

    def action_allocation_view(self) -> None:
        """Switch to GoalAllocationView (F3 — F-11b)."""
        from personal_finance.ui.screens.goal_allocation import GoalAllocationView  # noqa: PLC0415

        focused_goal_id = self._focused_goal_id()
        self.app.switch_screen(GoalAllocationView(initial_goal_id=focused_goal_id))

    def action_open_focused(self) -> None:
        """Open the dialog associated with the currently focused F6-able field."""
        ctx = self._f6_context()
        if ctx is None:
            return
        goal_id, field_type = ctx
        if field_type == "goal_amount":
            self._open_goal_value_dialog(goal_id)
        elif field_type == "inv_alloc":
            self._open_select_accounts_dialog(goal_id)
        elif field_type == "bank_alloc":
            self._open_bank_allocation_dialog(goal_id)

    def _open_goal_value_dialog(self, goal_id: int) -> None:
        """Open GoalValueDialog (F-9b) pre-populated with the goal's current strategy."""
        effective_date = self.app.effective_date  # type: ignore[attr-defined]
        try:
            params = self.app.services.goals.get_goal_value_params(  # type: ignore[attr-defined]
                goal_id, effective_date
            )
        except Exception as exc:
            logger.error("get_goal_value_params_failed", error=str(exc), exc_info=True)
            self.notify(f"Could not load goal data: {exc}", severity="error", timeout=5)
            return

        focus_id = f"goal-amount-{goal_id}"

        def _on_dismiss(saved: bool | None) -> None:
            if saved:
                self.run_worker(
                    self._load_data(focus_widget_id=focus_id),
                    exclusive=True,
                    name="load-goals",
                )

        self.app.push_screen(
            GoalValueDialog(
                goal_id,
                effective_date,
                initial_type=params.goal_type,
                initial_value=params.manual_value,
                initial_future_value=params.future_value,
                initial_start_date=params.start_date,
                initial_maturity_date=params.maturity_date,
                initial_discount_rate=params.discount_rate,
            ),
            callback=_on_dismiss,
        )

    def _open_select_accounts_dialog(self, goal_id: int) -> None:
        """Open SelectAccountsDialog (F-10) for the given goal."""
        effective_date = self.app.effective_date  # type: ignore[attr-defined]
        focus_id = f"inv-alloc-{goal_id}"

        def _on_dismiss(saved: bool | None) -> None:
            if saved:
                self.run_worker(
                    self._load_data(focus_widget_id=focus_id),
                    exclusive=True,
                    name="load-goals",
                )

        self.app.push_screen(
            SelectAccountsDialog(goal_id, effective_date),
            callback=_on_dismiss,
        )

    def _open_bank_allocation_dialog(self, goal_id: int) -> None:
        """Open BankAccountAllocationDialog (F-11) for the given goal."""
        effective_date = self.app.effective_date  # type: ignore[attr-defined]
        try:
            is_autofill = self.query_one(f"#gr-{goal_id}", GoalRow).is_autofill_bank
        except Exception:
            is_autofill = False

        focus_id = f"bank-alloc-{goal_id}"

        def _on_dismiss(saved: bool | None) -> None:
            if saved:
                self.run_worker(
                    self._load_data(focus_widget_id=focus_id),
                    exclusive=True,
                    name="load-goals",
                )

        self.app.push_screen(
            BankAccountAllocationDialog(goal_id, effective_date, is_autofill=is_autofill),
            callback=_on_dismiss,
        )

    def action_discard_goal(self) -> None:
        """Open ConfirmationDialog to soft-delete the focused goal (F8 — G-OP-4)."""
        goal_id = self._focused_goal_id()
        if goal_id is None:
            return
        try:
            row = self.query_one(f"#gr-{goal_id}", GoalRow)
            goal_name = row._row.name
        except Exception:
            goal_name = str(goal_id)

        def _on_confirmed(confirmed: bool | None) -> None:
            if confirmed:
                self.run_worker(
                    self._do_discard_goal(goal_id),
                    exclusive=False,
                    name=f"discard-goal-{goal_id}",
                )

        self.app.push_screen(
            ConfirmationDialog(f"Discard goal '{goal_name}'?"),
            callback=_on_confirmed,
        )

    # ── Workers ───────────────────────────────────────────────────────────────

    async def _load_data(self, *, focus_widget_id: str | None = None) -> None:
        """G-OP-1: Load goals summary and populate the screen.

        Args:
            focus_widget_id: If provided, restore focus to the widget with this
                ID after mounting rows (TUI Principle §2 — focus must return to
                the field that opened the dialog). Defaults to first Input.
        """
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            summary: GoalsSummary = await self.app.services.goals.get_goals_summary(as_of)  # type: ignore[attr-defined]
            # Cache for incremental overclaim updates — avoids re-fetching on every edit.
            self._total_bank_claims = sum((r.bank_allocation for r in summary.rows), Decimal("0"))
            self._bank_balance = summary.total_bank_balance
            content = self.query_one("#gl-content", VerticalScroll)
            await content.remove_children()
            if summary.rows:
                await content.mount(*[GoalRow(r) for r in summary.rows])
                if focus_widget_id is not None:
                    self._restore_focus(focus_widget_id)
                else:
                    try:
                        content.query("Input").first(Input).focus()
                    except Exception:
                        pass
            else:
                await content.mount(
                    Static("No goals yet — press F2 to create one.", classes="gl-empty")
                )
            self._refresh_overclaim_display()
        except Exception as exc:
            logger.error("goals_load_failed", error=str(exc), exc_info=True)
            content = self.query_one("#gl-content", VerticalScroll)
            await content.remove_children()
            await content.mount(Static(f"Error loading goals: {exc}"))

    async def _do_update_name(self, goal_id: int, new_name: str) -> None:
        """Persist a goal name change (no reload)."""
        try:
            self.app.services.goals.update_goal_name(goal_id, new_name)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.error("update_goal_name_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save name: {exc}", severity="error", timeout=5)

    async def _do_update_goal_scalar(self, goal_id: int, new_value: Decimal) -> None:
        """Persist a Manual goal target change; update Difference in-place."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.goals.update_goal_scalar_value(goal_id, new_value, as_of)  # type: ignore[attr-defined]
            try:
                row = self.query_one(f"#gr-{goal_id}", GoalRow)
                if row.is_autofill_bank and row.current_goal_target is not None:
                    self._total_bank_claims += new_value - row.current_goal_target
                row.update_goal_target(new_value)
            except Exception:
                pass
            self._refresh_overclaim_display()
        except Exception as exc:
            logger.error("update_goal_scalar_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save goal value: {exc}", severity="error", timeout=5)

    async def _do_update_bank_scalar(self, goal_id: int, new_amount: Decimal) -> None:
        """Persist a Scalar bank-claim change; update Difference in-place."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.goals.update_goal_bank_scalar(goal_id, new_amount, as_of)  # type: ignore[attr-defined]
            try:
                row = self.query_one(f"#gr-{goal_id}", GoalRow)
                self._total_bank_claims += new_amount - row.current_bank_alloc
                row.update_bank_alloc(new_amount)
            except Exception:
                pass
            self._refresh_overclaim_display()
        except Exception as exc:
            logger.error("update_bank_scalar_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save bank allocation: {exc}", severity="error", timeout=5)

    async def _do_discard_goal(self, goal_id: int) -> None:
        """G-OP-4: Soft-delete a goal and remove its row."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.goals.discard_goal(goal_id, as_of)  # type: ignore[attr-defined]
            try:
                self.query_one(f"#gr-{goal_id}", GoalRow).remove()
            except Exception:
                pass
        except Exception as exc:
            logger.error("discard_goal_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to discard goal: {exc}", severity="error", timeout=5)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _restore_focus(self, widget_id: str) -> None:
        """Restore focus to the widget with ``widget_id`` after a data reload.

        Handles :class:`F6OpenableField` containers (focuses the visible child),
        :class:`GoldBorderDisplay` (directly focusable), and plain inputs.
        Falls back silently if the widget is not found.
        """
        try:
            widget = self.query_one(f"#{widget_id}")
            if isinstance(widget, F6OpenableField):
                for child in widget.children:
                    if child.display:
                        child.focus()
                        return
            else:
                widget.focus()
        except Exception:
            pass

    def _refresh_overclaim_display(self) -> None:
        """Update the overclaim banner from cached bank-claim and bank-balance totals.

        No service call is needed — the screen maintains incremental running
        totals after every Scalar and AutoFill edit.
        """
        overclaim = self._total_bank_claims - self._bank_balance
        widget = self.query_one("#gl-overclaim", Static)
        if overclaim > Decimal("0"):
            widget.update(f"[!] Bank accounts are overclaimed by {MoneyInput.format(overclaim)}")
            widget.add_class("visible")
        else:
            widget.update("")
            widget.remove_class("visible")

    def _f6_context(self) -> tuple[int, str] | None:
        """Return ``(goal_id, field_type)`` for the focused F6-able widget, or None.

        ``field_type`` is one of ``"goal_amount"``, ``"inv_alloc"``, ``"bank_alloc"``.
        """
        focused = self.focused
        if focused is None:
            return None

        # Child of an F6OpenableField (Input or GoldBorderDisplay inside the composite).
        parent = focused.parent
        if isinstance(parent, F6OpenableField):
            fid = parent.id or ""
            if fid.startswith("goal-amount-"):
                try:
                    return (int(fid.removeprefix("goal-amount-")), "goal_amount")
                except ValueError:
                    return None
            if fid.startswith("bank-alloc-"):
                try:
                    return (int(fid.removeprefix("bank-alloc-")), "bank_alloc")
                except ValueError:
                    return None

        # Direct GoldBorderDisplay for the Investment Allocation column.
        if isinstance(focused, GoldBorderDisplay):
            fid = focused.id or ""
            if fid.startswith("inv-alloc-"):
                try:
                    return (int(fid.removeprefix("inv-alloc-")), "inv_alloc")
                except ValueError:
                    return None

        return None

    def _focused_goal_id(self) -> int | None:
        """Return the goal_id of the GoalRow that contains the focused widget, or None."""
        widget = self.focused
        while widget is not None:
            if isinstance(widget, GoalRow):
                return widget.goal_id
            widget = widget.parent  # type: ignore[assignment]
        return None
