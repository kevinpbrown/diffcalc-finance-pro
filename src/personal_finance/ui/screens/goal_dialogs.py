"""Goals modal dialogs — Flows F-9a, F-9b, F-10, and F-11.

Implements:
- GoalValueForm               — reusable form widget for the goal valuation strategy
- CreateGoalDialog            (Flow F-9a) — create a new financial goal
- GoalValueDialog             (Flow F-9b) — edit the valuation strategy of an existing goal
- SelectAccountsDialog        (Flow F-10) — allocate investment accounts to a goal
- BankAccountAllocationDialog (Flow F-11) — configure bank-account allocation strategy
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import structlog
from rich.text import Text as RichText
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    Static,
)

from personal_finance.domain.goals.goal import calculate_monthly_payment, calculate_present_value
from personal_finance.service.application.goal_app_service import InvestmentAccountOption
from personal_finance.ui.palette import TEXT_DIM
from personal_finance.ui.screens.dialogs import ModalDialogMixin
from personal_finance.ui.widgets.date_input import DateInput
from personal_finance.ui.widgets.inputs import (
    AppCheckbox,
    AppSelect,
    MoneyInput,
    PercentInput,
    TextInput,
)

logger = structlog.get_logger(__name__)


_GOAL_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("Manual", "manual"),
    ("Present value", "pv"),
    ("No target", "none"),
]


class GoalValueForm(Widget):
    """Reusable form body for creating or editing a goal's valuation strategy.

    Displays a Type dropdown (Manual / Present value / No target) and the
    matching conditional section:
    - Manual: a single Value numeric input.
    - Present value: four PV inputs plus live Current goal and Monthly pymt displays.
    - No target: nothing additional.

    Used by :class:`CreateGoalDialog` (F-9a) and will be reused by
    ``GoalValueDialog`` (F-9b) in the follow-on slice.

    Args:
        effective_date: Session effective date used for live PMT computation
            and as the default initial value for date inputs.
        initial_type: Pre-selected goal type (``"manual"``, ``"pv"``, or ``"none"``).
            Defaults to ``"manual"``.
        initial_value: Pre-filled target amount for Manual goals.
        initial_future_value: Pre-filled future value for PV goals.
        initial_start_date: Pre-filled savings start date for PV goals.
        initial_maturity_date: Pre-filled maturity date for PV goals.
        initial_discount_rate: Pre-filled annual discount rate as a fraction
            (e.g. ``Decimal("0.05")`` for 5%) for PV goals.
    """

    DEFAULT_CSS = """
    GoalValueForm .gvf-row {
        height: 3;
        layout: horizontal;
    }
    GoalValueForm .gvf-label {
        width: 16;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    GoalValueForm .gvf-field {
        width: 1fr;
        height: 3;
    }
    GoalValueForm .gvf-static {
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: #ffffff;
        padding: 0 1;
    }
    GoalValueForm #pv-section {
        height: auto;
    }
    GoalValueForm #manual-section {
        height: 3;
    }
    """

    def __init__(
        self,
        effective_date: date,
        *,
        initial_type: str = "manual",
        initial_value: Decimal | None = None,
        initial_future_value: Decimal | None = None,
        initial_start_date: date | None = None,
        initial_maturity_date: date | None = None,
        initial_discount_rate: Decimal | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Store initial values for rendering."""
        super().__init__(id=id, classes=classes)
        self._effective_date = effective_date
        self._initial_type = initial_type
        self._initial_value = initial_value
        self._initial_future_value = initial_future_value
        self._initial_start_date = initial_start_date
        self._initial_maturity_date = initial_maturity_date
        self._initial_discount_rate = initial_discount_rate

    def compose(self) -> ComposeResult:
        """Render the Type dropdown and conditional form sections."""
        # Type dropdown row
        with Horizontal(classes="gvf-row"):
            yield Label("Type:", classes="gvf-label")
            yield AppSelect(
                _GOAL_TYPE_OPTIONS,
                value=self._initial_type,
                allow_blank=False,
                id="gvf-type-select",
                classes="gvf-field",
            )

        # Manual section
        with Horizontal(classes="gvf-row", id="manual-section"):
            yield Label("Value:", classes="gvf-label")
            yield MoneyInput(
                value=MoneyInput.format(self._initial_value, placeholder=""),
                id="gvf-manual-value",
                classes="gvf-field",
                placeholder="$ 0.00",
            )

        # PV section (all rows together so they hide/show as a unit)
        dr_initial = (
            self._initial_discount_rate * Decimal("100")
            if self._initial_discount_rate is not None
            else None
        )
        start_dt = self._initial_start_date or self._effective_date
        mat_dt = self._initial_maturity_date or self._effective_date

        with Vertical(id="pv-section"):
            with Horizontal(classes="gvf-row"):
                yield Label("Future value:", classes="gvf-label")
                yield MoneyInput(
                    value=MoneyInput.format(self._initial_future_value, placeholder=""),
                    id="gvf-future-value",
                    classes="gvf-field",
                    placeholder="$ 0.00",
                )
            with Horizontal(classes="gvf-row"):
                yield Label("Savings start:", classes="gvf-label")
                yield DateInput(value=start_dt, id="gvf-start-date", classes="gvf-field")
            with Horizontal(classes="gvf-row"):
                yield Label("Maturity date:", classes="gvf-label")
                yield DateInput(value=mat_dt, id="gvf-maturity-date", classes="gvf-field")
            with Horizontal(classes="gvf-row"):
                yield Label("Discount rate:", classes="gvf-label")
                yield PercentInput(
                    value=PercentInput.format(dr_initial, placeholder=""),
                    id="gvf-discount-rate",
                    classes="gvf-field",
                    placeholder="5%",
                )
            with Horizontal(classes="gvf-row"):
                yield Label("Current goal:", classes="gvf-label")
                yield Static("—", id="gvf-current-goal", classes="gvf-static")
            with Horizontal(classes="gvf-row"):
                yield Label("Monthly pymt:", classes="gvf-label")
                yield Static("—", id="gvf-monthly-pymt", classes="gvf-static")

    def on_mount(self) -> None:
        """Apply initial section visibility based on the starting type."""
        self._sync_sections()

    def on_select_changed(self, event: AppSelect.Changed) -> None:
        """Show/hide conditional sections when the type dropdown changes."""
        if event.select.id == "gvf-type-select":
            event.stop()
            self._sync_sections()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Recompute live PV display when the numeric PV inputs change."""
        if event.input.id in ("gvf-future-value", "gvf-discount-rate"):
            event.stop()
            self._update_pv_display()

    def on_date_input_date_changed(self, event: DateInput.DateChanged) -> None:
        """Recompute live PV display when a date input commits."""
        if event.date_input.id in ("gvf-start-date", "gvf-maturity-date"):
            event.stop()
            self._update_pv_display()

    # ── Public API ──────────────────────────────────────────────────────────────

    def get_value_type(self) -> str:
        """Return the currently selected goal type (``'manual'``, ``'pv'``, or ``'none'``)."""
        try:
            val = self.query_one("#gvf-type-select", AppSelect).value
            return str(val) if val is not AppSelect.NULL else "manual"
        except Exception:
            return "manual"

    def get_manual_value(self) -> Decimal | None:
        """Return the Manual Value input as a Decimal, or None if blank.

        Raises:
            InvalidOperation: If the input is non-empty but not a valid number.
        """
        raw = self.query_one("#gvf-manual-value", MoneyInput).value.strip()
        return MoneyInput.parse(raw) if raw else None

    def get_pv_params(self) -> tuple[Decimal, date | None, date | None, Decimal]:
        """Return ``(future_value, start_date, maturity_date, discount_rate_fraction)``.

        The discount_rate is returned as a fraction (0.05 for an entry of 5.00).

        Raises:
            InvalidOperation: If future value or discount rate is not a valid number.
        """
        fv = MoneyInput.parse(self.query_one("#gvf-future-value", MoneyInput).value)
        start_dt = self.query_one("#gvf-start-date", DateInput).date
        mat_dt = self.query_one("#gvf-maturity-date", DateInput).date
        dr_pct = PercentInput.parse(self.query_one("#gvf-discount-rate", PercentInput).value)
        dr = dr_pct / Decimal("100")
        return fv, start_dt, mat_dt, dr

    def focus_first_input(self) -> None:
        """Focus the Type select (the first interactive element in this form)."""
        try:
            self.query_one("#gvf-type-select", AppSelect).focus()
        except Exception:
            pass

    def validate(self) -> str | None:
        """Validate the current form state.

        Returns:
            A human-readable error message, or ``None`` if the form is valid.
        """
        vtype = self.get_value_type()
        if vtype == "manual":
            raw = self.query_one("#gvf-manual-value", MoneyInput).value.strip()
            if raw:
                try:
                    MoneyInput.parse(raw)
                except InvalidOperation:
                    return "Value must be a valid number."
        elif vtype == "pv":
            fv_raw = self.query_one("#gvf-future-value", MoneyInput).value.strip()
            if not fv_raw:
                return "Future value is required."
            dr_raw = self.query_one("#gvf-discount-rate", PercentInput).value.strip()
            if not dr_raw:
                return "Discount rate is required."
            try:
                fv, start_dt, mat_dt, dr = self.get_pv_params()
            except InvalidOperation:
                return "Future value and discount rate must be valid numbers."
            if start_dt is None:
                return "Savings start date is invalid."
            if mat_dt is None:
                return "Maturity date is invalid."
            if mat_dt <= start_dt:
                return "Maturity date must be after savings start date."
            if dr < Decimal("0"):
                return "Discount rate cannot be negative."
        return None

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _sync_sections(self) -> None:
        """Show the section matching the current type; hide the others."""
        vtype = self.get_value_type()
        self.query_one("#manual-section").display = vtype == "manual"
        self.query_one("#pv-section").display = vtype == "pv"
        if vtype == "pv":
            self._update_pv_display()

    def _update_pv_display(self) -> None:
        """Recompute and display live Current goal (PV) and Monthly pymt (PMT)."""
        pv_widget = self.query_one("#gvf-current-goal", Static)
        pmt_widget = self.query_one("#gvf-monthly-pymt", Static)

        try:
            fv_raw = self.query_one("#gvf-future-value", MoneyInput).value.strip()
            if not fv_raw:
                pv_widget.update("—")
                pmt_widget.update("—")
                return
            fv = MoneyInput.parse(fv_raw)

            start_dt = self.query_one("#gvf-start-date", DateInput).date
            mat_dt = self.query_one("#gvf-maturity-date", DateInput).date

            dr_raw = self.query_one("#gvf-discount-rate", PercentInput).value.strip()
            if not dr_raw:
                pv_widget.update("—")
                pmt_widget.update("—")
                return
            dr = PercentInput.parse(dr_raw) / Decimal("100")

            if start_dt is None or mat_dt is None or mat_dt <= start_dt:
                pv_widget.update("—")
                pmt_widget.update("—")
                return

            pv = calculate_present_value(fv, dr, start_dt, mat_dt)
            pv_widget.update(f"$ {pv:,.2f}")

            pmt = calculate_monthly_payment(fv, dr, self._effective_date, mat_dt)
            if pmt is None:
                pmt_widget.update("N/A")
                return
            pmt_widget.update(f"$ {pmt:,.2f}")

        except (InvalidOperation, ZeroDivisionError, OverflowError, Exception):
            pv_widget.update("—")
            pmt_widget.update("—")


class CreateGoalDialog(ModalDialogMixin, ModalScreen[int | None]):
    """Modal dialog to create a new financial goal — Flow F-9a.

    Yields the new goal's database ID on success, or ``None`` on cancel.

    The Type dropdown defaults to Manual. Switching to Present value shows
    the four PV inputs with live-computed Current goal and Monthly pymt
    displays. Switching to No target hides all value inputs.

    The ``GoalValueForm`` body is structured to be reused by ``GoalValueDialog``
    (F-9b) in the follow-on slice.

    Args:
        effective_date: Session effective date for PV computation and service calls.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    CreateGoalDialog .cgd-row {
        height: 3;
        layout: horizontal;
    }
    CreateGoalDialog .cgd-label {
        width: 16;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    CreateGoalDialog .cgd-field {
        width: 1fr;
        height: 3;
    }
    """

    def __init__(self, effective_date: date) -> None:
        """Store the effective date."""
        super().__init__()
        self._effective_date = effective_date

    def compose(self) -> ComposeResult:
        """Render the Create Goal form with Name, GoalValueForm, and buttons."""
        with Vertical(classes="dialog"):
            yield Static("Create Goal", classes="dialog--title")
            with VerticalScroll(id="cgd-scroll"):
                with Horizontal(classes="cgd-row"):
                    yield Label("Name:", classes="cgd-label")
                    yield TextInput(id="cgd-name", classes="cgd-field", placeholder="Goal name")
                yield GoalValueForm(self._effective_date, id="cgd-form")
            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="btn-cancel")
                yield Button("Create", id="btn-create", variant="primary")

    def on_mount(self) -> None:
        """Focus the Name input on open."""
        self.query_one("#cgd-name", TextInput).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Cancel or attempt goal creation."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-create":
            self._do_create()

    def action_cancel(self) -> None:
        """Esc closes the dialog without saving."""
        self.dismiss(None)

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _do_create(self) -> None:
        """Validate and call the service to create the goal, then dismiss."""
        name = self.query_one("#cgd-name", TextInput).value.strip()
        if not name:
            self.notify("Goal name is required.", severity="error", timeout=3)
            self.query_one("#cgd-name", TextInput).focus()
            return

        form = self.query_one("#cgd-form", GoalValueForm)
        error = form.validate()
        if error:
            self.notify(error, severity="error", timeout=4)
            return

        vtype = form.get_value_type()
        try:
            if vtype == "manual":
                try:
                    value = form.get_manual_value()
                except InvalidOperation:
                    self.notify("Value must be a valid number.", severity="error", timeout=3)
                    return
                new_id: int = self.app.services.goals.create_goal(  # type: ignore[attr-defined]
                    name=name,
                    value_type="manual",
                    as_of=self._effective_date,
                    value=value,
                )
            elif vtype == "pv":
                try:
                    fv, start_dt, mat_dt, dr = form.get_pv_params()
                except InvalidOperation:
                    self.notify("PV parameters must be valid numbers.", severity="error", timeout=3)
                    return
                new_id = self.app.services.goals.create_goal(  # type: ignore[attr-defined]
                    name=name,
                    value_type="pv",
                    as_of=self._effective_date,
                    future_value=fv,
                    start_date=start_dt,
                    maturity_date=mat_dt,
                    discount_rate=dr,
                )
            else:  # "none"
                new_id = self.app.services.goals.create_goal(  # type: ignore[attr-defined]
                    name=name,
                    value_type="none",
                    as_of=self._effective_date,
                )

            self.dismiss(new_id)

        except Exception as exc:
            logger.error("create_goal_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to create goal: {exc}", severity="error", timeout=5)


class GoalValueDialog(ModalDialogMixin, ModalScreen[bool | None]):
    """Modal dialog to edit a goal's valuation strategy — Flow F-9b.

    Same layout as :class:`CreateGoalDialog` but without the Name field; buttons
    are ``[Cancel]`` / ``[ Save ]``. The form is pre-populated with the goal's
    current strategy so the user can change type and/or parameters in one step.

    Yields ``True`` on a successful save, or ``None`` on cancel.

    Args:
        goal_id: Primary key of the goal being edited.
        effective_date: Session effective date for PV computation and service calls.
        initial_type: Pre-selected goal type (``"manual"``, ``"pv"``, or ``"none"``).
        initial_value: Pre-filled target amount for Manual goals.
        initial_future_value: Pre-filled future value for PV goals.
        initial_start_date: Pre-filled savings start date for PV goals.
        initial_maturity_date: Pre-filled maturity date for PV goals.
        initial_discount_rate: Pre-filled annual discount rate as a fraction for PV goals.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        goal_id: int,
        effective_date: date,
        *,
        initial_type: str = "manual",
        initial_value: Decimal | None = None,
        initial_future_value: Decimal | None = None,
        initial_start_date: date | None = None,
        initial_maturity_date: date | None = None,
        initial_discount_rate: Decimal | None = None,
    ) -> None:
        """Store the goal identity and pre-fill values."""
        super().__init__()
        self._goal_id = goal_id
        self._effective_date = effective_date
        self._initial_type = initial_type
        self._initial_value = initial_value
        self._initial_future_value = initial_future_value
        self._initial_start_date = initial_start_date
        self._initial_maturity_date = initial_maturity_date
        self._initial_discount_rate = initial_discount_rate

    def compose(self) -> ComposeResult:
        """Render the Edit Goal Value form with GoalValueForm and Save/Cancel buttons."""
        with Vertical(classes="dialog"):
            yield Static("Edit Goal Value", classes="dialog--title")
            with VerticalScroll(id="gvd-scroll"):
                yield GoalValueForm(
                    self._effective_date,
                    initial_type=self._initial_type,
                    initial_value=self._initial_value,
                    initial_future_value=self._initial_future_value,
                    initial_start_date=self._initial_start_date,
                    initial_maturity_date=self._initial_maturity_date,
                    initial_discount_rate=self._initial_discount_rate,
                    id="gvd-form",
                )
            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="btn-cancel")
                yield Button("Save", id="btn-save", variant="primary")

    def on_mount(self) -> None:
        """Focus the Type select (first interactive element) on open."""
        self.query_one("#gvd-form", GoalValueForm).focus_first_input()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Cancel or attempt to save the goal value strategy change."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._do_save()

    def action_cancel(self) -> None:
        """Esc closes the dialog without saving."""
        self.dismiss(None)

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _do_save(self) -> None:
        """Validate form and call the service to update the goal value strategy."""
        form = self.query_one("#gvd-form", GoalValueForm)
        error = form.validate()
        if error:
            self.notify(error, severity="error", timeout=4)
            return

        vtype = form.get_value_type()
        try:
            if vtype == "manual":
                try:
                    value = form.get_manual_value()
                except InvalidOperation:
                    self.notify("Value must be a valid number.", severity="error", timeout=3)
                    return
                self.app.services.goals.update_goal_value_strategy(  # type: ignore[attr-defined]
                    self._goal_id,
                    value_type="manual",
                    as_of=self._effective_date,
                    value=value,
                )
            elif vtype == "pv":
                try:
                    fv, start_dt, mat_dt, dr = form.get_pv_params()
                except InvalidOperation:
                    self.notify("PV parameters must be valid numbers.", severity="error", timeout=3)
                    return
                self.app.services.goals.update_goal_value_strategy(  # type: ignore[attr-defined]
                    self._goal_id,
                    value_type="pv",
                    as_of=self._effective_date,
                    future_value=fv,
                    start_date=start_dt,
                    maturity_date=mat_dt,
                    discount_rate=dr,
                )
            else:  # "none"
                self.app.services.goals.update_goal_value_strategy(  # type: ignore[attr-defined]
                    self._goal_id,
                    value_type="none",
                    as_of=self._effective_date,
                )
            self.dismiss(True)
        except Exception as exc:
            logger.error("update_goal_value_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save: {exc}", severity="error", timeout=5)


# ── SelectAccountsDialog (Flow F-10) ──────────────────────────────────────────


class AccountListItem(ListItem):
    """One item in the SelectAccountsDialog account list.

    Renders a checkbox indicator (``[ ]`` / ``[x]`` / ``[-]``), the account
    name, and the account balance in a horizontal row.  Items assigned to
    another goal show ``[-]``, are coloured grey, and their checkbox cannot
    be toggled.

    Args:
        option: Account data from the application service.
    """

    DEFAULT_CSS = f"""
    AccountListItem > Horizontal {{
        height: 3;
        padding: 0 1;
    }}
    AccountListItem .ali-checkbox {{
        width: 5;
        height: 3;
        content-align: left middle;
        color: #ffffff;
    }}
    AccountListItem .ali-name {{
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: #ffffff;
    }}
    AccountListItem .ali-balance {{
        width: 16;
        height: 3;
        content-align: right middle;
        color: #ffffff;
    }}
    AccountListItem.blocked-item .ali-checkbox,
    AccountListItem.blocked-item .ali-name,
    AccountListItem.blocked-item .ali-balance {{
        color: {TEXT_DIM};
    }}
    """

    def __init__(self, option: InvestmentAccountOption) -> None:
        """Store option data and initial selection state."""
        super().__init__()
        self._option = option
        self._selected = option.is_selected

    @property
    def is_blocked(self) -> bool:
        """True when this account is assigned to another active goal."""
        return self._option.blocking_goal_name is not None

    @property
    def is_selected(self) -> bool:
        """True when this account is currently selected for the goal."""
        return self._selected

    @property
    def account_id(self) -> int:
        """Primary key of the investment account."""
        return self._option.account_id

    def on_mount(self) -> None:
        """Apply greyed-out class and disable navigation for blocked accounts."""
        if self.is_blocked:
            self.add_class("blocked-item")
            self.disabled = True

    def compose(self) -> ComposeResult:
        """Render checkbox indicator, account name, and balance."""
        if self.is_blocked:
            indicator = "[-]"
        elif self._selected:
            indicator = "[x]"
        else:
            indicator = "[ ]"

        display_name = (
            f"{self._option.name} ({self._option.blocking_goal_name})"
            if self._option.blocking_goal_name
            else self._option.name
        )
        balance_str = f"$ {self._option.balance:,.2f}" if self._option.balance is not None else ""

        with Horizontal():
            # markup=False: Rich would silently eat "[x]" as an unknown markup tag.
            yield Static(
                RichText(indicator),
                id=f"ali-cb-{self._option.account_id}",
                classes="ali-checkbox",
            )
            yield Static(display_name, classes="ali-name")
            yield Static(balance_str, classes="ali-balance")

    def toggle(self) -> None:
        """Toggle selection state and update the checkbox indicator.

        No-op if the account is assigned to another goal.
        """
        if self.is_blocked:
            return
        self._selected = not self._selected
        indicator = "[x]" if self._selected else "[ ]"
        try:
            self.query_one(f"#ali-cb-{self._option.account_id}", Static).update(RichText(indicator))
        except Exception:
            pass


class SelectAccountsDialog(ModalScreen[bool | None]):
    """Modal dialog to allocate investment accounts to a goal — Flow F-10.

    Loads all active investment accounts asynchronously into a ``ListView``.
    Accounts assigned to another goal show ``[-]`` (greyed, cursor skips them
    for toggling). ``Up`` / ``Down`` move the list cursor; ``Space`` toggles
    the highlighted row; ``Esc`` cancels.

    Yields ``True`` on a successful save, or ``None`` on cancel.

    Args:
        goal_id: Primary key of the goal whose account allocation is being edited.
        effective_date: Session effective date for balance lookups.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, goal_id: int, effective_date: date) -> None:
        """Store goal identity and effective date."""
        super().__init__()
        self._goal_id = goal_id
        self._effective_date = effective_date

    def compose(self) -> ComposeResult:
        """Render the dialog shell; the list is populated asynchronously."""
        with Vertical(classes="dialog"):
            yield Static("Select Account(s)", classes="dialog--title")
            with Vertical(id="sad-container"):
                yield LoadingIndicator()
            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="btn-cancel")
                yield Button("Save", id="btn-save", variant="primary")

    def on_mount(self) -> None:
        """Start loading investment accounts."""
        self.run_worker(self._load_accounts(), exclusive=True, name="load-accounts")

    def on_key(self, event: Key) -> None:
        """Toggle the highlighted list item when Space or Enter is pressed.

        Only intercepts when the ListView itself is focused; if a button has
        focus, Enter/Space must reach the button unmodified.
        """
        if event.key in ("space", "enter"):
            try:
                lv = self.query_one("#sad-list", ListView)
                if self.focused is not lv:
                    return
                idx = lv.index
                if idx is not None:
                    items = list(lv.query(AccountListItem))
                    if 0 <= idx < len(items):
                        item = items[idx]
                        if not item.is_blocked:
                            item.toggle()
                            event.stop()
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Cancel or save the account allocation."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._do_save()

    def action_cancel(self) -> None:
        """Esc closes the dialog without saving."""
        self.dismiss(None)

    # ── Workers ────────────────────────────────────────────────────────────────

    async def _load_accounts(self) -> None:
        """Fetch accounts and mount a ListView with one AccountListItem per account."""
        try:
            options: list[
                InvestmentAccountOption
            ] = await self.app.services.goals.get_investment_accounts_for_dialog(  # type: ignore[attr-defined]
                self._goal_id, self._effective_date
            )
            container = self.query_one("#sad-container", Vertical)
            await container.remove_children()
            if options:
                items = [AccountListItem(opt) for opt in options]
                lv = ListView(*items, id="sad-list")
                await container.mount(lv)
                lv.focus()
            else:
                await container.mount(Static("No investment accounts found.", classes="sad-empty"))
                self.query_one("#btn-cancel", Button).focus()
        except Exception as exc:
            logger.error("load_accounts_failed", error=str(exc), exc_info=True)
            container = self.query_one("#sad-container", Vertical)
            await container.remove_children()
            await container.mount(Static(f"Error loading accounts: {exc}"))
            self.query_one("#btn-cancel", Button).focus()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _do_save(self) -> None:
        """Collect selected account IDs, call G-OP-5, then dismiss."""
        selected_ids = [
            item.account_id
            for item in self.query(AccountListItem)
            if item.is_selected and not item.is_blocked
        ]
        try:
            self.app.services.goals.update_goal_investment_allocation(  # type: ignore[attr-defined]
                self._goal_id, selected_ids
            )
            self.dismiss(True)
        except Exception as exc:
            logger.error("update_inv_alloc_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save: {exc}", severity="error", timeout=5)


# ── BankAccountAllocationDialog (Flow F-11) ───────────────────────────────────


class BankAccountAllocationDialog(ModalDialogMixin, ModalScreen[bool | None]):
    """Modal dialog to configure bank-account allocation strategy — Flow F-11.

    A single checkbox controls whether the goal uses AutoFill
    (``GoalBankPortionAutoFill``, checked) or Scalar (``GoalBankPortionScalar``,
    unchecked) for its bank allocation.  Saving calls G-OP-6.

    Yields ``True`` on a successful save, or ``None`` on cancel.

    Args:
        goal_id: Primary key of the goal being edited.
        effective_date: Session effective date; used when switching to Scalar
            ($0 initial entry dated to this day).
        is_autofill: Whether the goal currently uses AutoFill strategy;
            pre-populates the checkbox.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    BankAccountAllocationDialog AppCheckbox {
        height: 1;
        width: 100%;
        border: none;
        background: transparent;
        padding: 0 1;
    }
    BankAccountAllocationDialog AppCheckbox:focus {
        border: none;
        background: #0055cc;
    }
    """

    def __init__(self, goal_id: int, effective_date: date, *, is_autofill: bool) -> None:
        """Store goal identity and current bank allocation mode."""
        super().__init__()
        self._goal_id = goal_id
        self._effective_date = effective_date
        self._is_autofill = is_autofill

    def compose(self) -> ComposeResult:
        """Render the dialog with the single toggle row and Save/Cancel buttons."""
        with Vertical(classes="dialog"):
            yield Static("Bank Account Allocation", classes="dialog--title")
            yield AppCheckbox(
                "Fill difference from bank accounts",
                value=self._is_autofill,
                id="bad-fill-check",
            )
            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="btn-cancel")
                yield Button("Save", id="btn-save", variant="primary")

    def on_mount(self) -> None:
        """Focus the toggle row on open."""
        self.query_one("#bad-fill-check", AppCheckbox).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Cancel or save the bank allocation strategy change."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._do_save()

    def action_cancel(self) -> None:
        """Esc closes the dialog without saving."""
        self.dismiss(None)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _do_save(self) -> None:
        """Call G-OP-6 to update the bank allocation strategy, then dismiss."""
        fill_difference = self.query_one("#bad-fill-check", AppCheckbox).value
        try:
            if fill_difference:
                self.app.services.goals.switch_bank_to_autofill(  # type: ignore[attr-defined]
                    self._goal_id
                )
            else:
                self.app.services.goals.switch_bank_to_scalar(  # type: ignore[attr-defined]
                    self._goal_id, self._effective_date
                )
            self.dismiss(True)
        except Exception as exc:
            logger.error("switch_bank_alloc_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save: {exc}", severity="error", timeout=5)
