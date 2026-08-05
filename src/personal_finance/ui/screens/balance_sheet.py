"""Balance Sheet Summary screen — Flow F-4.

Displays all active accounts grouped into four sections with section totals and
net worth calculations. Simple account names and balances are editable in-place.
Investment accounts show a gold-bordered read-only balance; press F6 to open the
Investment Editor (Flow F-6).
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

from personal_finance.service.application.balance_sheet_app_service import (
    AccountDetail,
    AccountSummaryRow,
    BalanceSheetSection,
    BalanceSheetSummary,
    PersonOption,
)
from personal_finance.ui.palette import PANEL_FILL, TEXT_DIM
from personal_finance.ui.screens.balance_sheet_dialogs import AccountCreationDialog
from personal_finance.ui.screens.dialogs import ConfirmationDialog
from personal_finance.ui.widgets.inputs import GoldBorderDisplay, MoneyInput
from personal_finance.ui.widgets.split_footer import SplitFooter
from personal_finance.ui.widgets.summary_bar import SummaryBar

logger = structlog.get_logger(__name__)


# ── AccountRow ────────────────────────────────────────────────────────────────


class AccountRow(Widget):
    """A single editable account row.

    Simple accounts show a static name label and an editable balance Input.
    Investment accounts show a static name label and a gold-bordered
    :class:`GoldBorderDisplay` (focusable, read-only; F6 to drill in).

    Posts custom messages upward to the owning screen:
    - :class:`AccountRow.BalanceSubmitted`

    Args:
        row: Data contract row describing this account.
    """

    DEFAULT_CSS = f"""
    AccountRow {{
        layout: horizontal;
        height: 3;
        padding: 0 2;
    }}
    AccountRow Input {{
        height: 3;
    }}
    AccountRow .acct-name {{
        width: 1fr;
        min-width: 20;
        height: 3;
        content-align: left middle;
        color: {TEXT_DIM};
    }}
    AccountRow .acct-balance {{
        width: 20;
        margin-left: 1;
    }}
    AccountRow .acct-balance-readonly {{
        width: 20;
        height: 3;
        margin-left: 1;
    }}
    """

    class BalanceSubmitted(Message):
        """User submitted a modified simple account balance.

        Attributes:
            account_id: Primary key of the account.
            raw_value: The raw Input string value (unparsed).
        """

        def __init__(self, account_id: int, raw_value: str) -> None:
            """Store fields."""
            super().__init__()
            self.account_id = account_id
            self.raw_value = raw_value

    def __init__(self, row: AccountSummaryRow) -> None:
        """Initialise the row widget with the account data."""
        super().__init__(id=f"acct-row-{row.account_id}")
        self._row = row
        self._original_balance = MoneyInput.format(row.balance)

    @property
    def account_id(self) -> int:
        """Primary key of the account this row represents."""
        return self._row.account_id

    @property
    def account_name(self) -> str:
        """Display name of the account this row represents."""
        return self._row.name

    def compose(self) -> ComposeResult:
        """Render the name label and balance area."""
        yield Static(self._row.name, classes="acct-name")
        if self._row.is_investment:
            yield GoldBorderDisplay(
                self._original_balance,
                id=f"bal-{self._row.account_id}",
                classes="acct-balance-readonly",
            )
        else:
            yield MoneyInput(
                value=self._original_balance,
                id=f"bal-{self._row.account_id}",
                classes="acct-balance",
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Fire a balance-submitted message when the balance field is submitted.

        Focus advancement is handled by MoneyInput, so this handler must NOT
        also call focus_next().
        """
        event.stop()
        input_id = event.input.id or ""
        if input_id == f"bal-{self._row.account_id}":
            if event.value != self._original_balance:
                self.post_message(self.BalanceSubmitted(self._row.account_id, event.value))


# ── Section total row ─────────────────────────────────────────────────────────


class _SectionTotalRow(Horizontal):
    """A horizontal row displaying a section label and its running total."""

    def __init__(self, section: BalanceSheetSection, section_id: str) -> None:
        """Store section data for compose."""
        super().__init__(classes="bs-total-row")
        self._section = section
        self._section_id = section_id

    def compose(self) -> ComposeResult:
        """Render label and total amount."""
        yield Static(
            f"{self._section.label} Total",
            classes="bs-total-label",
        )
        yield Static(
            f"$ {self._section.total:>14,.2f}",
            id=f"total-{self._section_id}",
            classes="bs-total-amount",
        )


# ── BalanceSheetScreen ────────────────────────────────────────────────────────


class BalanceSheetScreen(Screen[None]):
    """Balance Sheet Summary screen — Flow F-4.

    Displays all active accounts in four sections with editable fields for
    simple account names and balances. Investment account balances are shown
    in a gold-bordered read-only display; press F6 to open the Investment Editor.
    """

    _persons: list[PersonOption] = []

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("f2", "new_asset", "New Asset", show=True),
        Binding("f3", "new_liability", "New Liability", show=True),
        Binding("f5", "refresh_data", "Refresh", show=True),
        Binding("f6", "open_investment", "Open", show=True),
        Binding("f7", "edit_account", "Edit Account", show=True),
        Binding("f8", "discard_account", "Discard", show=True),
    ]

    DEFAULT_CSS = f"""
    BalanceSheetScreen {{
        background: #000080;
    }}

    #bs-title-bar {{
        background: {PANEL_FILL};
        height: 3;
        border-bottom: solid #aaaaff;
        padding: 0 2;
    }}

    #bs-title {{
        color: #aaaaff;
        text-style: bold;
        width: 1fr;
        height: 3;
        content-align: left middle;
    }}

    #bs-date {{
        color: #aaaaaa;
        height: 3;
        content-align: right middle;
        width: 14;
    }}

    #bs-content {{
        background: #000080;
        padding: 0 1;
    }}

    .bs-section-label {{
        color: #aaaaff;
        text-style: bold;
        padding: 1 1 0 1;
        height: 2;
        content-align: left bottom;
    }}

    .bs-total-row {{
        height: 2;
        padding: 0 2;
        margin-bottom: 1;
    }}

    .bs-total-label {{
        color: #aaaaaa;
        width: 1fr;
        content-align: left middle;
        height: 2;
    }}

    .bs-total-amount {{
        color: #ffffff;
        width: 20;
        content-align: right middle;
        height: 2;
        padding-right: 2;
    }}

    """

    def compose(self) -> ComposeResult:
        """Render the title bar, scrollable content area, net worth bar, and footer."""
        with Horizontal(id="bs-title-bar"):
            yield Static("Balance Sheet", id="bs-title")
            yield Static("", id="bs-date")
        with VerticalScroll(id="bs-content", can_focus=False):
            yield LoadingIndicator()
        yield SummaryBar([("nw-left", "", "fill"), ("nw-right", "", 38)])
        yield SplitFooter({"open_investment", "edit_account", "discard_account"})

    def on_mount(self) -> None:
        """Show the effective date and kick off the data-load worker."""
        self.query_one("#bs-date", Static).update(
            str(self.app.effective_date)  # type: ignore[attr-defined]
        )
        self.run_worker(self._load_data(), exclusive=True, name="load-bs")

    def on_screen_resume(self) -> None:
        """Refresh data when returning from a child screen (e.g. Investment Editor)."""
        self.run_worker(self._refresh(), exclusive=True, name="load-bs")

    def on_key(self, event: Key) -> None:
        """Up/Down arrows navigate between focusable widgets."""
        if event.key == "down":
            self.focus_next()
            event.stop()
        elif event.key == "up":
            self.focus_previous()
            event.stop()

    def on_descendant_focus(self) -> None:
        """Refresh footer bindings when any descendant gains focus."""
        self.refresh_bindings()

    def on_descendant_blur(self) -> None:
        """Refresh footer bindings when any descendant loses focus."""
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Hide F6/F7/F8 from the footer unless the relevant widget type is focused."""
        if action == "open_investment":
            focused = self.focused
            return isinstance(focused, GoldBorderDisplay) and (focused.id or "").startswith("bal-")
        if action == "edit_account":
            focused = self.focused
            return focused is not None and (focused.id or "").startswith("bal-")
        if action == "discard_account":
            focused = self.focused
            return focused is not None and isinstance(focused.parent, AccountRow)
        return True

    # ── Incoming messages from AccountRow ─────────────────────────────────────

    def on_account_row_balance_submitted(self, event: AccountRow.BalanceSubmitted) -> None:
        """Parse and persist an updated simple account balance."""
        try:
            new_balance = MoneyInput.parse(event.raw_value)
        except InvalidOperation:
            self.notify(
                "Invalid balance — enter a numeric value.",
                severity="error",
                timeout=4,
            )
            return
        self.run_worker(
            self._do_update_balance(event.account_id, new_balance),
            exclusive=False,
            name=f"update-balance-{event.account_id}",
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_go_back(self) -> None:
        """Return to the Dashboard."""
        self.app.pop_screen()

    def action_refresh_data(self) -> None:
        """Reload all account data from the database (F5)."""
        self.run_worker(self._refresh(), exclusive=True, name="load-bs")

    def action_new_asset(self) -> None:
        """Open AccountCreationDialog for a new asset account (F2)."""
        if not self._persons:
            self.notify("No persons found in database.", severity="error", timeout=4)
            return
        self.app.push_screen(
            AccountCreationDialog("asset", self._persons),
            callback=self._on_account_created,
        )

    def action_new_liability(self) -> None:
        """Open AccountCreationDialog for a new liability account (F3)."""
        if not self._persons:
            self.notify("No persons found in database.", severity="error", timeout=4)
            return
        self.app.push_screen(
            AccountCreationDialog("liability", self._persons),
            callback=self._on_account_created,
        )

    def _on_account_created(self, new_id: int | None) -> None:
        """Reload the balance sheet after a new account is created."""
        if new_id is not None:
            self.run_worker(self._load_data(), exclusive=True, name="load-bs")

    def action_edit_account(self) -> None:
        """Open AccountCreationDialog in edit mode for the focused account (F7)."""
        focused = self.focused
        if focused is None:
            return
        fid = focused.id or ""
        if not fid.startswith("bal-"):
            return
        try:
            account_id = int(fid.removeprefix("bal-"))
        except ValueError:
            return
        try:
            detail: AccountDetail = (
                self.app.services.balance_sheet.get_account_detail(account_id)  # type: ignore[attr-defined]
            )
        except Exception as exc:
            logger.error("get_account_detail_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to load account: {exc}", severity="error", timeout=4)
            return
        side = "asset" if detail.is_asset else "liability"
        self.app.push_screen(
            AccountCreationDialog(side, self._persons, existing=detail),
            callback=self._on_account_edited,
        )

    def _on_account_edited(self, account_id: int | None) -> None:
        """Reload the balance sheet after an account is edited."""
        if account_id is not None:
            self.run_worker(self._load_data(), exclusive=True, name="load-bs")

    def action_open_investment(self) -> None:
        """Open the Investment Editor if an investment balance is focused (F6)."""
        focused = self.focused
        if not isinstance(focused, GoldBorderDisplay):
            return
        fid = focused.id or ""
        if not fid.startswith("bal-"):
            return
        try:
            account_id = int(fid.removeprefix("bal-"))
        except ValueError:
            return
        # Late import prevents a circular import with investment_editor.py.
        from personal_finance.ui.screens.investment_editor import (
            InvestmentEditorScreen,  # noqa: PLC0415
        )

        self.app.push_screen(InvestmentEditorScreen(account_id))

    def action_discard_account(self) -> None:
        """Open ConfirmationDialog to discard the focused account (F8)."""
        focused = self.focused
        if focused is None:
            return
        parent = focused.parent
        if not isinstance(parent, AccountRow):
            return
        account_id = parent.account_id
        account_name = parent.account_name

        def _on_confirmed(confirmed: bool | None) -> None:
            if confirmed:
                self.run_worker(
                    self._do_discard_account(account_id),
                    exclusive=False,
                    name=f"discard-account-{account_id}",
                )

        self.app.push_screen(
            ConfirmationDialog(f"Discard account '{account_name}'?"),
            callback=_on_confirmed,
        )

    # ── Workers ───────────────────────────────────────────────────────────────

    async def _refresh(self) -> None:
        """Reload data and restore focus to the previously focused widget.

        Falls back to the default first-input focus when the previously focused
        widget no longer exists (e.g. after a discard).
        """
        focused_id = self.focused.id if self.focused else None
        await self._load_data()
        if focused_id:
            try:
                self.query_one(f"#{focused_id}").focus()
            except Exception:
                pass

    async def _load_data(self) -> None:
        """Load the balance sheet summary and populate the screen."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            summary: BalanceSheetSummary = (
                await self.app.services.balance_sheet.get_summary(as_of)  # type: ignore[attr-defined]
            )
            self._persons = (
                self.app.services.balance_sheet.get_persons()  # type: ignore[attr-defined]
            )
            content = self.query_one("#bs-content", VerticalScroll)
            await content.remove_children()
            await content.mount(*_build_content_widgets(summary))
            self._set_net_worth(summary)
            # Place focus on the first account balance field.
            try:
                self.query(".acct-balance").first().focus()
            except Exception:
                try:
                    self.query(".acct-balance-readonly").first().focus()
                except Exception:
                    pass
        except Exception as exc:
            logger.error("balance_sheet_load_failed", error=str(exc), exc_info=True)
            content = self.query_one("#bs-content", VerticalScroll)
            await content.remove_children()
            await content.mount(Static(f"Error loading balance sheet: {exc}"))

    async def _do_discard_account(self, account_id: int) -> None:
        """BS-OP-4: Soft-delete the account and reload the balance sheet."""
        try:
            self.app.services.balance_sheet.discard_account(  # type: ignore[attr-defined]
                account_id,
                self.app.effective_date,  # type: ignore[attr-defined]
            )
            await self._refresh()
        except Exception as exc:
            logger.error("discard_account_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to discard account: {exc}", severity="error", timeout=5)

    async def _do_update_balance(self, account_id: int, new_balance: Decimal) -> None:
        """Persist a balance change and refresh totals.

        MoneyInput reformats the displayed value on submit, so no explicit
        reformat is needed here after the async save completes.
        """
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.balance_sheet.update_simple_account_balance(  # type: ignore[attr-defined]
                account_id, as_of, new_balance
            )
            await self._refresh_totals()
        except Exception as exc:
            logger.error("update_balance_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save balance: {exc}", severity="error", timeout=5)

    async def _refresh_totals(self) -> None:
        """Re-fetch the summary and update totals and net worth in-place."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            summary: BalanceSheetSummary = (
                await self.app.services.balance_sheet.get_summary(as_of)  # type: ignore[attr-defined]
            )
            for section, sid in [
                (summary.current_assets, "ca"),
                (summary.long_term_assets, "la"),
                (summary.current_liabilities, "cl"),
                (summary.long_term_liabilities, "ll"),
            ]:
                self.query_one(f"#total-{sid}", Static).update(f"$ {section.total:>13,.2f}")
            self._set_net_worth(summary)
        except Exception as exc:
            logger.error("refresh_totals_failed", error=str(exc), exc_info=True)

    def _set_net_worth(self, summary: BalanceSheetSummary) -> None:
        """Update the fixed net worth bar with current summary figures."""
        bar = self.query_one(SummaryBar)
        bar.update_item("nw-left", f"Current Net Worth:  $ {summary.current_net_worth:>13,.2f}")
        bar.update_item("nw-right", f"Total Net Worth: $ {summary.total_net_worth:>13,.2f}")


# ── Module-level helpers ──────────────────────────────────────────────────────


def _build_content_widgets(summary: BalanceSheetSummary) -> list[Widget]:
    """Build the ordered list of widgets to mount into the scroll area.

    Args:
        summary: Populated balance sheet data.

    Returns:
        Flat list of widgets ready to pass to ``VerticalScroll.mount()``.
    """
    widgets: list[Widget] = []

    for section, section_id in [
        (summary.current_assets, "ca"),
        (summary.long_term_assets, "la"),
        (summary.current_liabilities, "cl"),
        (summary.long_term_liabilities, "ll"),
    ]:
        widgets.append(Static(section.label, classes="bs-section-label"))
        for row in section.accounts:
            widgets.append(AccountRow(row))
        widgets.append(_SectionTotalRow(section, section_id))

    return widgets
