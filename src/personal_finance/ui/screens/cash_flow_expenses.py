"""Cash Flow Expenses screen — Flow F-13 and F-13a.

This module implements the Expenses view of the Cash Flow module:
  - :class:`CashFlowExpensesView`  (F-13) — grouped expense list with inline amount editing
  - :class:`ExpenseDialog`         (F-13a) — create / edit expense modal

Both are built on the shared ``TwoPaneScreen`` base and use the same
``_CashFlowNavPane`` imported from ``cash_flow.py``.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import ClassVar

import structlog
from rich.text import Text as RichText
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Input, Static

from personal_finance.domain.cash_flow.expense import (
    HouseholdExpenseClassification,
    HouseholdExpenseFrequency,
    HouseholdExpenseSource,
)
from personal_finance.service.application.cash_flow_app_service import (
    ExpenseRow,
    ExpenseSummaryData,
    ExpensesViewData,
)
from personal_finance.ui.palette import BORDER_STRUCTURAL, TEXT_DIM
from personal_finance.ui.screens.base import TwoPaneScreen
from personal_finance.ui.screens.cash_flow import (
    _NAV_EXPENSES,
    _NAV_REPORT,
    _CashFlowNavPane,
    _NavEntry,
    _NavKind,
)
from personal_finance.ui.screens.dialogs import ConfirmationDialog, ModalDialogMixin
from personal_finance.ui.widgets.inputs import AppSelect, MoneyInput, TextInput

logger = structlog.get_logger(__name__)

_D0 = Decimal("0")

# ── Source / Frequency option lists ───────────────────────────────────────────

_SOURCE_OPTIONS: list[tuple[str, HouseholdExpenseSource]] = [
    ("Bank", HouseholdExpenseSource.BANK),
    ("Credit Card", HouseholdExpenseSource.CREDIT),
    ("Other", HouseholdExpenseSource.OTHER),
]

_FREQ_OPTIONS: list[tuple[str, HouseholdExpenseFrequency]] = [
    ("Regular", HouseholdExpenseFrequency.REGULAR),
    ("Irregular", HouseholdExpenseFrequency.IRREGULAR),
]

_CLASSIFICATION_LABELS: dict[HouseholdExpenseClassification, str] = {
    HouseholdExpenseClassification.HOME: "Home",
    HouseholdExpenseClassification.AUTO: "Auto",
    HouseholdExpenseClassification.OTHER: "Other",
}


# ── Expense row widget ─────────────────────────────────────────────────────────


class _ExpenseRow(Widget):
    """One expense row: static name label + inline amount MoneyInput."""

    DEFAULT_CSS = """
    _ExpenseRow {
        layout: horizontal;
        height: 3;
        padding: 0 1;
    }
    _ExpenseRow ._er-name {
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    _ExpenseRow ._er-amount {
        width: 20;
        height: 3;
    }
    """

    def __init__(self, expense_id: int, name: str, amount_str: str) -> None:
        """Store expense metadata for lookup by the owning screen."""
        super().__init__(id=f"cfexpr-row-{expense_id}")
        self._expense_id = expense_id
        self._name = name
        self._amount_str = amount_str

    @property
    def expense_id(self) -> int:
        """Primary key of the associated HouseholdExpense."""
        return self._expense_id

    def compose(self) -> ComposeResult:
        """Render the name label and amount input."""
        yield Static(f"  {self._name}", classes="_er-name")
        yield MoneyInput(value=self._amount_str, classes="_er-amount")


# ── Summary widget ─────────────────────────────────────────────────────────────


class _ExpenseSummaryWidget(Static):
    """Cross-tab summary: Source × Frequency with totals.

    Pinned at the bottom of the right pane, above the footer.
    Call :meth:`update_summary` to refresh after any save.
    """

    DEFAULT_CSS = f"""
    _ExpenseSummaryWidget {{
        height: 8;
        background: #000060;
        padding: 0 1;
        border-top: solid {BORDER_STRUCTURAL};
        color: #aaaaaa;
    }}
    """

    def update_summary(self, data: ExpenseSummaryData) -> None:
        """Rerender the cross-tab with new data."""
        self.update(self._build_text(data))

    @staticmethod
    def _build_text(data: ExpenseSummaryData) -> RichText:
        def _fmt(v: Decimal) -> str:
            return f"$ {v:>10,.2f}"

        bank_total = data.bank_regular + data.bank_irregular
        credit_total = data.credit_regular + data.credit_irregular
        other_total = data.other_regular + data.other_irregular
        reg_total = data.bank_regular + data.credit_regular + data.other_regular
        irreg_total = data.bank_irregular + data.credit_irregular + data.other_irregular
        grand_total = reg_total + irreg_total

        text = RichText("Summary (Monthly)\n", style="bold #aaaaff")
        text.append(
            f"{'':13}  {'Regular':>12}  {'Irregular':>12}  {'Total':>12}\n",
            style=TEXT_DIM,
        )
        for label, reg, irreg, total in [
            ("Bank", data.bank_regular, data.bank_irregular, bank_total),
            ("Credit Card", data.credit_regular, data.credit_irregular, credit_total),
            ("Other", data.other_regular, data.other_irregular, other_total),
        ]:
            text.append(
                f"{label:<13}  {_fmt(reg):>12}  {_fmt(irreg):>12}  ",
                style="#aaaaaa",
            )
            text.append(f"{_fmt(total):>12}\n", style="bold #ffffff")
        text.append(
            f"{'Total':<13}  {_fmt(reg_total):>12}  {_fmt(irreg_total):>12}"
            f"  {_fmt(grand_total):>12}",
            style="bold #ffffff",
        )
        return text


# ── ExpenseDialog (F-13a) ─────────────────────────────────────────────────────


class ExpenseDialog(ModalDialogMixin, ModalScreen[int | None]):
    """Create / Edit Expense dialog — Flow F-13a.

    In **create mode** pass ``category`` (the classification pre-set by the
    function key pressed).  In **edit mode** pass ``expense`` (the row data to
    pre-populate).  Exactly one of the two must be supplied.

    Dismisses with the expense primary key on success, or ``None`` on cancel.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    ExpenseDialog .exp-row {
        height: 3;
        layout: horizontal;
    }
    ExpenseDialog .exp-label {
        width: 12;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    ExpenseDialog .exp-field {
        width: 1fr;
        height: 3;
    }
    """

    def __init__(
        self,
        category: HouseholdExpenseClassification | None = None,
        expense: ExpenseRow | None = None,
    ) -> None:
        """Initialise in create or edit mode.

        Args:
            category: Classification for create mode (HOME / AUTO / OTHER).
            expense: Existing row data for edit mode.
        """
        super().__init__()
        assert (category is None) != (expense is None), (
            "Exactly one of category or expense must be supplied"
        )
        self._category = category
        self._expense = expense

    @property
    def _is_create(self) -> bool:
        return self._category is not None

    @property
    def _dialog_title(self) -> str:
        if self._is_create:
            label = _CLASSIFICATION_LABELS[self._category]  # type: ignore[index]
            return f"New {label} Expense"
        return "Edit Expense"

    def compose(self) -> ComposeResult:
        """Render the form inside a dialog container."""
        initial_name = "" if self._is_create else (self._expense.name if self._expense else "")
        initial_amount = (
            MoneyInput.format(_D0)
            if self._is_create
            else MoneyInput.format(self._expense.amount if self._expense else _D0)
        )
        initial_source = (
            HouseholdExpenseSource.BANK
            if self._is_create
            else (self._expense.source if self._expense else HouseholdExpenseSource.BANK)
        )
        initial_freq = (
            HouseholdExpenseFrequency.REGULAR
            if self._is_create
            else (self._expense.frequency if self._expense else HouseholdExpenseFrequency.REGULAR)
        )
        action_label = "Create" if self._is_create else "Save"

        with VerticalScroll(classes="dialog"):
            yield Static(self._dialog_title, classes="dialog--title")
            with Widget(classes="exp-row"):
                yield Static("Name:", classes="exp-label")
                yield TextInput(value=initial_name, id="exp-name", classes="exp-field")
            with Widget(classes="exp-row"):
                yield Static("Amount:", classes="exp-label")
                yield MoneyInput(value=initial_amount, id="exp-amount", classes="exp-field")
            with Widget(classes="exp-row"):
                yield Static("Source:", classes="exp-label")
                yield AppSelect(
                    _SOURCE_OPTIONS,
                    value=initial_source,
                    id="exp-source",
                    classes="exp-field",
                )
            with Widget(classes="exp-row"):
                yield Static("Frequency:", classes="exp-label")
                yield AppSelect(
                    _FREQ_OPTIONS,
                    value=initial_freq,
                    id="exp-freq",
                    classes="exp-field",
                )
            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="btn-cancel", variant="default")
                yield Button(action_label, id="btn-save", variant="primary")

    def on_mount(self) -> None:
        """Focus the Name field — Textual never auto-focuses inside a modal."""
        self.query_one("#exp-name", TextInput).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Cancel or save depending on which button was pressed."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._save()

    def action_cancel(self) -> None:
        """Esc dismisses without saving."""
        self.dismiss(None)

    def _save(self) -> None:
        """Validate fields and call the appropriate service method."""
        name = self.query_one("#exp-name", TextInput).value.strip()
        if not name:
            self.notify("Name is required.", severity="error", timeout=3)
            return

        raw_source = self.query_one("#exp-source", AppSelect).value
        raw_freq = self.query_one("#exp-freq", AppSelect).value
        if raw_source is AppSelect.NULL or raw_freq is AppSelect.NULL:
            self.notify("Source and Frequency are required.", severity="error", timeout=3)
            return

        try:
            amount = MoneyInput.parse(self.query_one("#exp-amount", MoneyInput).value)
        except InvalidOperation:
            self.notify("Invalid amount.", severity="error", timeout=3)
            return

        source: HouseholdExpenseSource = raw_source  # type: ignore[assignment]
        freq: HouseholdExpenseFrequency = raw_freq  # type: ignore[assignment]
        as_of = self.app.effective_date  # type: ignore[attr-defined]

        try:
            if self._is_create:
                assert self._category is not None
                new_id = self.app.services.cash_flow.create_expense(  # type: ignore[attr-defined]
                    name=name,
                    amount=amount,
                    classification=self._category,
                    source=source,
                    frequency=freq,
                    as_of=as_of,
                )
                self.dismiss(new_id)
            else:
                assert self._expense is not None
                self.app.services.cash_flow.update_expense(  # type: ignore[attr-defined]
                    expense_id=self._expense.expense_id,
                    name=name,
                    amount=amount,
                    classification=self._expense.classification,
                    source=source,
                    frequency=freq,
                    as_of=as_of,
                )
                self.dismiss(self._expense.expense_id)
        except ValueError as exc:
            self.notify(str(exc), severity="error", timeout=4)


# ── CashFlowExpensesView (F-13) ───────────────────────────────────────────────


class CashFlowExpensesView(TwoPaneScreen):
    """Cash Flow Expenses View — Flow F-13.

    Left pane: ``_CashFlowNavPane`` with "Expenses" active.
    Right pane: VerticalScroll of expense groups (Home / Auto / Other), each
    with a header label and per-expense rows containing a static name and an
    inline MoneyInput.
    Summary: fixed cross-tab table pinned below the split and above the footer.

    ``Esc`` returns directly to the Dashboard (same as the other Cash Flow views).
    """

    SCREEN_TITLE = "Cash Flow"
    _CONTEXTUAL_ACTIONS: ClassVar[frozenset[str]] = frozenset({"edit_expense", "discard_expense"})

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_to_dashboard", "Back", show=True),
        Binding("f2", "new_expense_home", "New Home", show=True),
        Binding("f3", "new_expense_auto", "New Auto", show=True),
        Binding("f4", "new_expense_other", "New Other", show=True),
        Binding("f7", "edit_expense", "Edit Expense", show=True),
        Binding("f8", "discard_expense", "Discard", show=True),
    ]

    DEFAULT_CSS = f"""
    #cfexpr-right-header {{
        height: 1;
        margin: 1 0 0 0;
        padding: 0 1;
        color: #aaaaff;
        text-style: bold;
    }}

    #cfexpr-col-header {{
        layout: horizontal;
        height: 1;
        padding: 0 1;
        margin-bottom: 0;
        color: {TEXT_DIM};
    }}

    #cfexpr-col-header ._ch-name {{
        width: 1fr;
    }}

    #cfexpr-col-header ._ch-amount {{
        width: 20;
    }}

    #cfexpr-expense-scroll {{
        height: 1fr;
    }}

    #cfexpr-expense-list {{
        height: auto;
    }}

    .cfexpr-group-header {{
        height: 1;
        padding: 0 1;
        color: #aaaaff;
        text-style: bold;
        margin-top: 1;
    }}
    """

    def __init__(self) -> None:
        """Initialise screen state."""
        super().__init__()
        self._nav_items: list[_NavEntry] = []
        self._n_persons: int = 0
        self._selected_idx: int = 0
        self._expense_rows: list[ExpenseRow] = []

    def _compose_left_pane(self) -> ComposeResult:
        """Yield the nav pane."""
        yield _CashFlowNavPane(id="tps-left", on_select=self._navigate_to)

    def _compose_right_pane(self) -> ComposeResult:
        """Yield the expenses list with summary pinned to the bottom of the right pane."""
        with Vertical(id="tps-right"):
            yield Static("Expenses", id="cfexpr-right-header")
            with Widget(id="cfexpr-col-header"):
                yield Static("Name", classes="_ch-name")
                yield Static("Amount", classes="_ch-amount")
            with VerticalScroll(id="cfexpr-expense-scroll", can_focus=False):
                yield Widget(id="cfexpr-expense-list")
            yield _ExpenseSummaryWidget(id="cfexpr-summary")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Set effective date and start loading nav + expenses."""
        super().on_mount()
        self.run_worker(self._load_nav_and_expenses(), exclusive=True, name="cfexpr-load")

    # ── Keyboard handling ─────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        """Navigate the left nav pane with Up/Down/Enter when it has focus."""
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
            if self._nav_items and self._nav_items[self._selected_idx].kind == _NavKind.EXPENSES:
                self._focus_first_expense()

    # ── check_action ──────────────────────────────────────────────────────────

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """F7 and F8 are only enabled when focus is on an expense row's MoneyInput.

        All other actions return True explicitly — Textual's run_action uses a
        truthiness check on the return value, so None silently disables the action.
        """
        if action in ("edit_expense", "discard_expense"):
            focused = self.focused
            return isinstance(focused, MoneyInput) and isinstance(focused.parent, _ExpenseRow)
        return True

    def on_descendant_focus(self) -> None:
        """Refresh footer bindings when any descendant gains focus."""
        self.refresh_bindings()

    def on_descendant_blur(self) -> None:
        """Refresh footer bindings when any descendant loses focus."""
        self.refresh_bindings()

    # ── Input submitted ───────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """On Enter in an expense row amount: persist the new amount."""
        row = event.input.parent
        if not isinstance(row, _ExpenseRow):
            return
        try:
            amount = MoneyInput.parse(event.input.value)
        except InvalidOperation:
            self.notify("Invalid amount.", severity="error", timeout=3)
            return
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.cash_flow.update_expense_amount(  # type: ignore[attr-defined]
                expense_id=row.expense_id,
                amount=amount,
                as_of=as_of,
            )
            self.run_worker(self._refresh_summary(), exclusive=False, name="cfexpr-summary")
        except ValueError as exc:
            self.notify(str(exc), severity="error", timeout=4)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_go_to_dashboard(self) -> None:
        """Return directly to the Dashboard (Esc)."""
        from personal_finance.ui.screens.dashboard import DashboardScreen  # noqa: PLC0415

        self.app.switch_screen(DashboardScreen())

    def action_new_expense_home(self) -> None:
        """F2: open ExpenseDialog to create a Home expense."""
        self._open_create_dialog(HouseholdExpenseClassification.HOME)

    def action_new_expense_auto(self) -> None:
        """F3: open ExpenseDialog to create an Auto expense."""
        self._open_create_dialog(HouseholdExpenseClassification.AUTO)

    def action_new_expense_other(self) -> None:
        """F4: open ExpenseDialog to create an Other expense."""
        self._open_create_dialog(HouseholdExpenseClassification.OTHER)

    def action_edit_expense(self) -> None:
        """F7: open ExpenseDialog to edit the focused expense row."""
        expense = self._get_focused_expense_row()
        if expense is None:
            return
        self.app.push_screen(
            ExpenseDialog(expense=expense),
            callback=self._on_expense_saved,
        )

    def action_discard_expense(self) -> None:
        """F8: confirm and discard the focused expense row."""
        expense = self._get_focused_expense_row()
        if expense is None:
            return

        def _on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                return
            as_of = self.app.effective_date  # type: ignore[attr-defined]
            try:
                self.app.services.cash_flow.discard_expense(  # type: ignore[attr-defined]
                    expense_id=expense.expense_id,
                    as_of=as_of,
                )
                self.run_worker(
                    self._load_expenses(focus_expense_id=None),
                    exclusive=True,
                    name="cfexpr-reload",
                )
            except ValueError as exc:
                self.notify(str(exc), severity="error", timeout=4)

        self.app.push_screen(
            ConfirmationDialog(f"Discard expense '{expense.name}'?"),
            callback=_on_confirm,
        )

    # ── Navigation helpers ────────────────────────────────────────────────────

    def _navigate_to(self, new_idx: int) -> None:
        """Handle left-pane item selection."""
        entry = self._nav_items[new_idx]
        self._selected_idx = new_idx
        self.query_one("#tps-left", _CashFlowNavPane).update(
            self._nav_items, self._selected_idx, self._n_persons
        )

        if entry.kind == _NavKind.PERSON:
            assert entry.profile_id is not None
            from personal_finance.ui.screens.cash_flow import (  # noqa: PLC0415
                CashFlowPersonProfileView,
            )

            self.app.switch_screen(CashFlowPersonProfileView(entry.profile_id))
        elif entry.kind == _NavKind.REPORT:
            from personal_finance.ui.screens.cash_flow_report import (  # noqa: PLC0415
                HouseholdCashFlowReportView,
            )

            self.app.switch_screen(HouseholdCashFlowReportView())

    # ── Dialog helpers ────────────────────────────────────────────────────────

    def _open_create_dialog(self, category: HouseholdExpenseClassification) -> None:
        self.app.push_screen(
            ExpenseDialog(category=category),
            callback=self._on_expense_saved,
        )

    def _on_expense_saved(self, expense_id: int | None) -> None:
        """Reload expense list after a dialog save; focus the saved row."""
        if expense_id is None:
            return
        self.run_worker(
            self._load_expenses(focus_expense_id=expense_id),
            exclusive=True,
            name="cfexpr-reload",
        )

    # ── Focus helpers ─────────────────────────────────────────────────────────

    def _get_focused_expense_row(self) -> ExpenseRow | None:
        """Return the ExpenseRow whose MoneyInput currently has focus, or None."""
        focused = self.focused
        if not isinstance(focused, MoneyInput):
            return None
        parent = focused.parent
        if not isinstance(parent, _ExpenseRow):
            return None
        expense_id = parent.expense_id
        return next((r for r in self._expense_rows if r.expense_id == expense_id), None)

    def _focus_row(self, expense_id: int) -> None:
        """Focus the MoneyInput in the row for the given expense_id."""
        try:
            row = self.query_one(f"#cfexpr-row-{expense_id}", _ExpenseRow)
            row.query_one(MoneyInput).focus()
        except Exception:
            pass

    def _focus_first_expense(self) -> None:
        """Focus the first expense row MoneyInput."""
        try:
            self.query_one("#cfexpr-expense-scroll").query(MoneyInput).first().focus()
        except Exception:
            pass

    # ── Async workers ─────────────────────────────────────────────────────────

    async def _load_nav_and_expenses(self) -> None:
        """Build the nav pane and load the initial expense list."""
        try:
            person_items = self.app.services.cash_flow.get_person_nav_items()  # type: ignore[attr-defined]
            self._n_persons = len(person_items)
            self._nav_items = [
                _NavEntry(
                    kind=_NavKind.PERSON,
                    label=item.person_name,
                    profile_id=item.profile_id,
                )
                for item in person_items
            ] + [_NAV_EXPENSES, _NAV_REPORT]

            # "Expenses" is the item right after the persons
            self._selected_idx = self._n_persons  # index of _NAV_EXPENSES

            self.query_one("#tps-left", _CashFlowNavPane).update(
                self._nav_items, self._selected_idx, self._n_persons
            )
            await self._load_expenses(focus_expense_id=None)
        except Exception as exc:
            logger.error("cfexpr_load_nav_failed", error=str(exc), exc_info=True)
            self.notify(f"Error loading expenses: {exc}", severity="error", timeout=5)

    async def _load_expenses(self, *, focus_expense_id: int | None) -> None:
        """Reload expense rows and summary; optionally focus a specific row."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            data: ExpensesViewData = self.app.services.cash_flow.get_expenses_view_data(as_of)  # type: ignore[attr-defined]
            self._expense_rows = data.home + data.auto + data.other

            expense_list = self.query_one("#cfexpr-expense-list", Widget)
            await expense_list.remove_children()

            widgets: list[Widget] = []
            for group_label, group_rows in [
                ("Home", data.home),
                ("Auto", data.auto),
                ("Other", data.other),
            ]:
                if not group_rows:
                    continue
                widgets.append(Static(group_label, classes="cfexpr-group-header"))
                for row in group_rows:
                    widgets.append(
                        _ExpenseRow(
                            expense_id=row.expense_id,
                            name=row.name,
                            amount_str=MoneyInput.format(row.amount),
                        )
                    )

            if widgets:
                await expense_list.mount(*widgets)

            summary_widget = self.query_one("#cfexpr-summary", _ExpenseSummaryWidget)
            summary_widget.update_summary(data.summary)

            if focus_expense_id is not None:
                self.call_after_refresh(lambda: self._focus_row(focus_expense_id))

        except Exception as exc:
            logger.error("cfexpr_load_expenses_failed", error=str(exc), exc_info=True)
            self.notify(f"Error loading expenses: {exc}", severity="error", timeout=5)

    async def _refresh_summary(self) -> None:
        """Recompute and re-render the summary table without rebuilding rows."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            data: ExpensesViewData = self.app.services.cash_flow.get_expenses_view_data(as_of)  # type: ignore[attr-defined]
            self._expense_rows = data.home + data.auto + data.other
            self.query_one("#cfexpr-summary", _ExpenseSummaryWidget).update_summary(data.summary)
        except Exception as exc:
            logger.error("cfexpr_refresh_summary_failed", error=str(exc), exc_info=True)
