"""Household Cash Flow Report screen — Flows F-14 and F-15.

This module contains:
  - :class:`HouseholdCashFlowReportView`    (F-14) — read-only report with
    gold-bordered automated contribution fields.
  - :class:`AutomatedContributionDialog`    (F-15) — create / edit modal.

Both are built on the shared infrastructure established by the other Cash Flow
screens (``TwoPaneScreen``, ``_CashFlowNavPane``, ``_NavKind``).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import ClassVar

import structlog
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Static

from personal_finance.service.application.cash_flow_app_service import (
    AccountOption,
    ContributionRow,
    GoalOption,
    ReportViewData,
)
from personal_finance.ui.palette import ACCENT_CYAN, TEXT_DIM, TEXT_HINT
from personal_finance.ui.screens.base import TwoPaneScreen
from personal_finance.ui.screens.cash_flow import (
    _NAV_EXPENSES,
    _NAV_REPORT,
    _CashFlowNavPane,
    _NavEntry,
    _NavKind,
)
from personal_finance.ui.screens.dialogs import ConfirmationDialog, ModalDialogMixin
from personal_finance.ui.widgets.inputs import AppSelect, GoldBorderDisplay, MoneyInput, TextInput

logger = structlog.get_logger(__name__)

_D0 = Decimal("0")
_D12 = Decimal("12")


# ── Formatting helpers ─────────────────────────────────────────────────────────


def _fmt(value: Decimal) -> str:
    """Format a positive monetary amount as a fixed 16-char string.

    The result is '$ ' followed by a 14-char right-aligned number.
    """
    return f"$ {value:>14,.2f}"


def _fmt_deduction(value: Decimal) -> str:
    """Format a deduction as a fixed 17-char string: '$ (' + 13-char number + ')'.

    One character wider than :func:`_fmt` so the closing bracket lands one
    column past the last cent digit, which then lines up with the last cent
    digit of non-deduction amounts (see the matching padding adjustment on
    ``._rr-amount``/``._cr-amount`` in this module).
    """
    return f"$ ({value:>13,.2f})"


# ── Report row widgets ─────────────────────────────────────────────────────────


class _ReportRow(Widget):
    """A label + formatted-amount pair displayed as a single read-only line.

    Height is 1 (no border). Styling variants via CSS classes:
    - ``cfr-bold``: white bold text.
    - ``cfr-header``: dimmed header colour.
    """

    DEFAULT_CSS = f"""
    _ReportRow {{
        layout: horizontal;
        height: 1;
        padding: 0 1;
    }}
    _ReportRow ._rr-label {{
        width: 1fr;
        color: #aaaaaa;
        content-align: left middle;
    }}
    _ReportRow ._rr-amount {{
        width: 20;
        padding: 0 1 0 2;
        color: #aaaaaa;
        content-align: left middle;
    }}
    _ReportRow.cfr-bold ._rr-label,
    _ReportRow.cfr-bold ._rr-amount {{
        text-style: bold;
        color: #ffffff;
    }}
    _ReportRow.cfr-header ._rr-label,
    _ReportRow.cfr-header ._rr-amount {{
        color: {TEXT_DIM};
    }}
    """

    def __init__(
        self,
        label: str,
        amount_str: str,
        *,
        bold: bool = False,
        header: bool = False,
    ) -> None:
        """Initialise with a pre-formatted amount string."""
        cls_parts: list[str] = []
        if bold:
            cls_parts.append("cfr-bold")
        if header:
            cls_parts.append("cfr-header")
        super().__init__(classes=" ".join(cls_parts) if cls_parts else None)
        self._label = label
        self._amount_str = amount_str

    def compose(self) -> ComposeResult:
        """Yield label and amount statics."""
        yield Static(self._label, classes="_rr-label")
        yield Static(self._amount_str, classes="_rr-amount")


class _ContributionRow(Widget):
    """An automated contribution name label + GoldBorderDisplay amount.

    The GoldBorderDisplay is focusable and opens :class:`AutomatedContributionDialog`
    when F6 is pressed.  The widget ``id`` is ``'contrib-{contribution_id}'`` so
    the owning screen can derive the contribution primary key from a focused widget.
    """

    DEFAULT_CSS = """
    _ContributionRow {
        layout: horizontal;
        height: 3;
        padding: 0 1;
    }
    _ContributionRow ._cr-name {
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    _ContributionRow ._cr-amount {
        width: 20;
        padding: 0 0 0 1;
    }
    """

    def __init__(self, contribution_id: int, name: str, amount_str: str) -> None:
        """Store contribution data; set id for contribution-id derivation."""
        super().__init__(id=f"contrib-{contribution_id}")
        self._name = name
        self._amount_str = amount_str

    def compose(self) -> ComposeResult:
        """Yield the name label and gold-bordered amount display."""
        yield Static(f"    {self._name}", classes="_cr-name")
        yield GoldBorderDisplay(self._amount_str, classes="_cr-amount")


# ── AutomatedContributionDialog (F-15) ────────────────────────────────────────


class AutomatedContributionDialog(ModalDialogMixin, ModalScreen[int | None]):
    """Create / Edit Automated Contribution dialog — Flow F-15.

    In **create mode** pass no ``contribution`` argument.  In **edit mode** pass
    the :class:`~personal_finance.service.application.cash_flow_app_service.ContributionRow`
    to pre-populate fields.

    Dismisses with the contribution primary key on success, or ``None`` on cancel.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    AutomatedContributionDialog .acd-row {
        height: 3;
        layout: horizontal;
    }
    AutomatedContributionDialog .acd-label {
        width: 20;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    AutomatedContributionDialog .acd-field {
        width: 1fr;
        height: 3;
    }
    """

    def __init__(self, contribution: ContributionRow | None = None) -> None:
        """Initialise in create or edit mode.

        Args:
            contribution: Existing row data for edit mode; ``None`` for create mode.
        """
        super().__init__()
        self._contribution = contribution

    @property
    def _is_create(self) -> bool:
        return self._contribution is None

    def compose(self) -> ComposeResult:
        """Render the form fields inside a dialog container."""
        action_label = "Create" if self._is_create else "Save"

        with VerticalScroll(classes="dialog"):
            yield Static("Automated Contribution", classes="dialog--title")
            with Widget(classes="acd-row"):
                yield Static("Name:", classes="acd-label")
                yield TextInput(value="", id="acd-name", classes="acd-field")
            with Widget(classes="acd-row"):
                yield Static("Amount per month:", classes="acd-label")
                yield MoneyInput(value=MoneyInput.format(_D0), id="acd-amount", classes="acd-field")
            with Widget(classes="acd-row"):
                yield Static("From account:", classes="acd-label")
                yield AppSelect([], id="acd-from", classes="acd-field", allow_blank=True)
            with Widget(classes="acd-row"):
                yield Static("To account:", classes="acd-label")
                yield AppSelect([], id="acd-to", classes="acd-field", allow_blank=True)
            with Widget(classes="acd-row"):
                yield Static("Goal:", classes="acd-label")
                yield AppSelect([], id="acd-goal", classes="acd-field", allow_blank=True)
            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="btn-cancel", variant="default")
                yield Button(action_label, id="btn-save", variant="primary")

    def on_mount(self) -> None:
        """Populate dropdowns, pre-fill edit-mode values, then focus Name."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        svc = self.app.services.cash_flow  # type: ignore[attr-defined]

        bank_accounts: list[AccountOption] = svc.get_bank_account_options(as_of)
        investment_accounts: list[AccountOption] = svc.get_investment_account_options(as_of)
        goals: list[GoalOption] = svc.get_goal_options(as_of)

        from_select = self.query_one("#acd-from", AppSelect)
        to_select = self.query_one("#acd-to", AppSelect)
        goal_select = self.query_one("#acd-goal", AppSelect)

        from_select.set_options([(a.name, a.account_id) for a in bank_accounts])
        to_select.set_options([(a.name, a.account_id) for a in investment_accounts])
        goal_select.set_options([(g.name, g.goal_id) for g in goals])

        if self._contribution is not None:
            c = self._contribution
            self.query_one("#acd-name", TextInput).value = c.name
            self.query_one("#acd-amount", MoneyInput).value = MoneyInput.format(c.amount)
            from_select.value = c.source_account_id
            to_select.value = c.destination_account_id
            goal_select.value = c.target_goal_id

        self.query_one("#acd-name", TextInput).focus()

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
        """Validate all fields and call the appropriate service method."""
        name = self.query_one("#acd-name", TextInput).value.strip()
        if not name:
            self.notify("Name is required.", severity="error", timeout=3)
            return

        try:
            amount = MoneyInput.parse(self.query_one("#acd-amount", MoneyInput).value)
        except InvalidOperation:
            self.notify("Invalid amount.", severity="error", timeout=3)
            return

        from_val = self.query_one("#acd-from", AppSelect).value
        to_val = self.query_one("#acd-to", AppSelect).value
        goal_val = self.query_one("#acd-goal", AppSelect).value

        if from_val is AppSelect.NULL or to_val is AppSelect.NULL or goal_val is AppSelect.NULL:
            self.notify("All fields are required.", severity="error", timeout=3)
            return

        source_account_id: int = int(from_val)  # type: ignore[arg-type]
        destination_account_id: int = int(to_val)  # type: ignore[arg-type]
        target_goal_id: int = int(goal_val)  # type: ignore[arg-type]
        as_of = self.app.effective_date  # type: ignore[attr-defined]

        try:
            if self._is_create:
                new_id = self.app.services.cash_flow.create_automated_contribution(  # type: ignore[attr-defined]
                    name=name,
                    amount=amount,
                    source_account_id=source_account_id,
                    destination_account_id=destination_account_id,
                    target_goal_id=target_goal_id,
                    as_of=as_of,
                )
                self.dismiss(new_id)
            else:
                assert self._contribution is not None
                self.app.services.cash_flow.update_automated_contribution(  # type: ignore[attr-defined]
                    contribution_id=self._contribution.contribution_id,
                    name=name,
                    amount=amount,
                    source_account_id=source_account_id,
                    destination_account_id=destination_account_id,
                    target_goal_id=target_goal_id,
                    as_of=as_of,
                )
                self.dismiss(self._contribution.contribution_id)
        except ValueError as exc:
            self.notify(str(exc), severity="error", timeout=4)


# ── HouseholdCashFlowReportView (F-14) ────────────────────────────────────────


class HouseholdCashFlowReportView(TwoPaneScreen):
    """Household Cash Flow Report View — Flow F-14.

    Left pane: ``_CashFlowNavPane`` with "Household Cash Flow" active.
    Right pane: read-only scrollable report with gold-bordered automated
    contribution fields.

    Bindings:
    - ``Esc``  → Dashboard
    - ``F2``   → :class:`AutomatedContributionDialog` (create; always available)
    - ``F6``   → :class:`AutomatedContributionDialog` (edit; contextual)
    - ``F8``   → :class:`ConfirmationDialog` to discard focused contribution (contextual)

    ``F6`` and ``F8`` are only enabled when a :class:`_ContributionRow`'s
    :class:`GoldBorderDisplay` has focus.
    """

    SCREEN_TITLE = "Cash Flow"
    _CONTEXTUAL_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {"open_contribution", "discard_contribution"}
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_to_dashboard", "Back", show=True),
        Binding("f2", "add_contribution", "Add Contribution", show=True),
        Binding("f6", "open_contribution", "Open", show=True),
        Binding("f8", "discard_contribution", "Discard Contribution", show=True),
    ]

    DEFAULT_CSS = f"""
    HouseholdCashFlowReportView #tps-right {{
        padding: 0 1;
        overflow-y: auto;
    }}

    #cfr-right-header {{
        height: 1;
        margin: 1 1 1 1;
        color: #aaaaff;
        text-style: bold;
    }}

    #cfr-content {{
        height: auto;
    }}

    .cfr-sep {{
        height: 1;
        margin: 0 1;
        color: {ACCENT_CYAN};
    }}

    .cfr-section-label {{
        height: 1;
        padding: 0 1;
        color: #aaaaaa;
    }}

    .cfr-sub-label {{
        height: 1;
        padding: 0 1;
        color: {TEXT_DIM};
    }}

    .cfr-pct {{
        height: 1;
        padding: 0 1;
        color: {TEXT_DIM};
    }}

    .cfr-section-header {{
        height: 1;
        padding: 0 1;
        color: #aaaaff;
        text-style: bold;
    }}

    .cfr-empty {{
        height: 1;
        padding: 0 1;
        color: {TEXT_HINT};
    }}
    """

    def __init__(self) -> None:
        """Initialise screen state."""
        super().__init__()
        self._nav_items: list[_NavEntry] = []
        self._n_persons: int = 0
        self._selected_idx: int = 0
        self._report_data: ReportViewData | None = None

    # ── Composition ───────────────────────────────────────────────────────────

    def _compose_left_pane(self) -> ComposeResult:
        """Yield the nav pane with 'Household Cash Flow' active."""
        yield _CashFlowNavPane(id="tps-left", on_select=self._navigate_to)

    def _compose_right_pane(self) -> ComposeResult:
        """Yield the report right pane."""
        with VerticalScroll(id="tps-right", can_focus=False):
            yield Static("Household Cash Flow", id="cfr-right-header")
            yield Widget(id="cfr-content")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Set effective date and kick off nav + report loading."""
        super().on_mount()
        self.run_worker(self._load_nav_and_report(), exclusive=True, name="cfr-load")

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
            if self._nav_items and self._nav_items[self._selected_idx].kind == _NavKind.REPORT:
                self._focus_first_contribution()

    # ── check_action ──────────────────────────────────────────────────────────

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """F6 and F8 are only enabled when a contribution GoldBorderDisplay has focus.

        All other actions return ``True`` — ``None`` would silently disable them.
        """
        if action in ("open_contribution", "discard_contribution"):
            return self._get_focused_contribution_id() is not None
        return True

    def on_descendant_focus(self) -> None:
        """Refresh footer contextual bindings when focus changes."""
        self.refresh_bindings()

    def on_descendant_blur(self) -> None:
        """Refresh footer contextual bindings when focus leaves a descendant."""
        self.refresh_bindings()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_go_to_dashboard(self) -> None:
        """Esc: return to the Dashboard."""
        from personal_finance.ui.screens.dashboard import DashboardScreen  # noqa: PLC0415

        self.app.switch_screen(DashboardScreen())

    def action_add_contribution(self) -> None:
        """F2: open AutomatedContributionDialog in create mode."""
        self.app.push_screen(
            AutomatedContributionDialog(),
            callback=self._on_contribution_saved,
        )

    def action_open_contribution(self) -> None:
        """F6: open AutomatedContributionDialog in edit mode for the focused row."""
        contrib = self._get_focused_contribution_row()
        if contrib is None:
            return
        self.app.push_screen(
            AutomatedContributionDialog(contribution=contrib),
            callback=self._on_contribution_saved,
        )

    def action_discard_contribution(self) -> None:
        """F8: confirm and discard the focused automated contribution."""
        contrib = self._get_focused_contribution_row()
        if contrib is None:
            return

        def _on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                return
            as_of = self.app.effective_date  # type: ignore[attr-defined]
            try:
                self.app.services.cash_flow.discard_automated_contribution(  # type: ignore[attr-defined]
                    contribution_id=contrib.contribution_id,
                    as_of=as_of,
                )
                self.run_worker(
                    self._reload_report(focus_contribution_id=None),
                    exclusive=True,
                    name="cfr-reload",
                )
            except ValueError as exc:
                self.notify(str(exc), severity="error", timeout=4)

        self.app.push_screen(
            ConfirmationDialog(f"Discard contribution '{contrib.name}'?"),
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
        elif entry.kind == _NavKind.EXPENSES:
            from personal_finance.ui.screens.cash_flow_expenses import (  # noqa: PLC0415
                CashFlowExpensesView,
            )

            self.app.switch_screen(CashFlowExpensesView())

    # ── Dialog callbacks ──────────────────────────────────────────────────────

    def _on_contribution_saved(self, contribution_id: int | None) -> None:
        """Reload the report after create/edit; focus the saved row."""
        if contribution_id is None:
            return
        self.run_worker(
            self._reload_report(focus_contribution_id=contribution_id),
            exclusive=True,
            name="cfr-reload",
        )

    # ── Focus helpers ─────────────────────────────────────────────────────────

    def _get_focused_contribution_id(self) -> int | None:
        """Return the contribution_id of the focused row, or None."""
        focused = self.focused
        if not isinstance(focused, GoldBorderDisplay):
            return None
        parent = focused.parent
        if not isinstance(parent, _ContributionRow):
            return None
        widget_id = parent.id or ""
        if not widget_id.startswith("contrib-"):
            return None
        try:
            return int(widget_id[len("contrib-") :])
        except ValueError:
            return None

    def _get_focused_contribution_row(self) -> ContributionRow | None:
        """Return the ContributionRow data for the focused widget, or None."""
        contrib_id = self._get_focused_contribution_id()
        if contrib_id is None or self._report_data is None:
            return None
        return next(
            (c for c in self._report_data.contributions if c.contribution_id == contrib_id),
            None,
        )

    def _focus_contribution(self, contribution_id: int) -> None:
        """Focus the GoldBorderDisplay in the row for the given contribution_id."""
        try:
            row = self.query_one(f"#contrib-{contribution_id}", _ContributionRow)
            row.query_one(GoldBorderDisplay).focus()
        except Exception:
            pass

    def _focus_first_contribution(self) -> None:
        """Focus the first GoldBorderDisplay in the contributions list."""
        try:
            self.query(GoldBorderDisplay).first().focus()
        except Exception:
            pass

    # ── Async workers ─────────────────────────────────────────────────────────

    async def _load_nav_and_report(self) -> None:
        """Load nav pane items and the initial report data."""
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

            # "Household Cash Flow" is the last item
            self._selected_idx = len(self._nav_items) - 1

            self.query_one("#tps-left", _CashFlowNavPane).update(
                self._nav_items, self._selected_idx, self._n_persons
            )
            await self._reload_report(focus_contribution_id=None)
        except Exception as exc:
            logger.error("cfr_load_nav_failed", error=str(exc), exc_info=True)
            self.notify(f"Error loading report: {exc}", severity="error", timeout=5)

    async def _reload_report(self, *, focus_contribution_id: int | None) -> None:
        """Reload and repaint the right-pane report content."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            data: ReportViewData = self.app.services.cash_flow.get_report_view_data(as_of)  # type: ignore[attr-defined]
            self._report_data = data

            content = self.query_one("#cfr-content", Widget)
            await content.remove_children()

            widgets: list[Widget] = self._build_report_widgets(data)
            if widgets:
                await content.mount(*widgets)

            if focus_contribution_id is not None:
                self.call_after_refresh(lambda: self._focus_contribution(focus_contribution_id))
        except Exception as exc:
            logger.error("cfr_reload_failed", error=str(exc), exc_info=True)
            self.notify(f"Error loading report: {exc}", severity="error", timeout=5)

    def _build_report_widgets(self, data: ReportViewData) -> list[Widget]:
        """Construct the list of widgets to mount in the report content area."""
        widgets: list[Widget] = []

        # ── Income reconciliation ──────────────────────────────────────────────
        widgets.append(Static(""))
        widgets.append(_ReportRow("Total monthly gross income", _fmt(data.gross_monthly)))
        for line in data.rrsp_deduction_lines:
            widgets.append(
                _ReportRow(
                    f"  Less Automated RRSP for {line.person_name}",
                    _fmt_deduction(line.monthly_amount),
                )
            )
        widgets.append(_ReportRow("  Less taxes & other", _fmt_deduction(data.taxes_other_monthly)))
        widgets.append(_ReportRow("Total monthly net income", _fmt(data.net_monthly), bold=True))
        widgets.append(Static("─" * 42, classes="cfr-sep"))

        # ── Expense and contribution deductions ────────────────────────────────
        widgets.append(Static("Less:", classes="cfr-section-label"))
        widgets.append(
            _ReportRow("  Average monthly expenses", _fmt_deduction(data.avg_monthly_expenses))
        )
        if data.contributions:
            widgets.append(Static("  Automated contributions:", classes="cfr-sub-label"))
            for contrib in data.contributions:
                widgets.append(
                    _ContributionRow(
                        contribution_id=contrib.contribution_id,
                        name=contrib.name,
                        amount_str=_fmt_deduction(contrib.amount),
                    )
                )
            widgets.append(Static(""))

        # ── Monthly / annual retained ──────────────────────────────────────────
        widgets.append(
            _ReportRow("Total monthly retained", _fmt(data.total_monthly_retained), bold=True)
        )
        widgets.append(Static("─" * 42, classes="cfr-sep"))
        widgets.append(_ReportRow("Total annual retained", _fmt(data.total_annual_retained)))
        widgets.append(_ReportRow("Total net bonus", _fmt(data.total_net_bonus)))
        widgets.append(Static(""))
        widgets.append(
            _ReportRow("Total annual retained", _fmt(data.final_annual_retained), bold=True)
        )
        if data.gross_annual_total > _D0:
            pct = data.final_annual_retained / data.gross_annual_total * 100
            widgets.append(Static(f"  ({pct:.1f}% of gross family income)", classes="cfr-pct"))
        widgets.append(Static("─" * 42, classes="cfr-sep"))

        # ── Goal contributions (annualized) ────────────────────────────────────
        widgets.append(Static("Goal Contributions (Annualized)", classes="cfr-section-header"))
        if data.goal_contributions:
            widgets.append(_ReportRow("Goal", "Amount", header=True))
            for goal_line in data.goal_contributions:
                widgets.append(_ReportRow(goal_line.goal_name, _fmt(goal_line.annual_amount)))
        else:
            widgets.append(Static("  No goal contributions yet.", classes="cfr-empty"))

        return widgets
