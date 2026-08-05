"""Investment Editor screen — Flow F-6.

Displays and edits the cash balance and holdings of an InvestmentAccount.

- Cash balance row: editable (BS-OP-7).
- Holdings table:
    - Listed: Name read-only (from API), Symbol read-only, Quantity editable, Total
      read-only (calculated), Allocation gold-bordered read-only (F6 → F-7b).
    - Exact: Name editable, Symbol/Quantity disabled, Total editable,
      Allocation gold-bordered read-only (F6 → F-7b).
- F2 → AddHoldingDialog (F-7a).
- F8 → ConfirmationDialog to discard holding (BS-OP-11).
- Esc → back to BalanceSheetSummary.
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
    HoldingRow as HoldingRowData,
)
from personal_finance.service.application.balance_sheet_app_service import (
    InvestmentDetails,
)
from personal_finance.ui.palette import PANEL_FILL, TEXT_HINT
from personal_finance.ui.screens.balance_sheet_dialogs import AddHoldingDialog
from personal_finance.ui.screens.dialogs import ConfirmationDialog
from personal_finance.ui.widgets.inputs import (
    GoldBorderDisplay,
    MoneyInput,
    QuantityInput,
    TextInput,
)
from personal_finance.ui.widgets.split_footer import SplitFooter
from personal_finance.ui.widgets.summary_bar import SummaryBar

logger = structlog.get_logger(__name__)


# ── HoldingTableRow ───────────────────────────────────────────────────────


class HoldingTableRow(Widget):
    """One row in the holdings table.

    Listed: Name (Static), Symbol (Input), Quantity (Input), Total (Static),
    Allocation (GoldBorderDisplay).

    Exact: Name (Input), Symbol/Qty (Static "—"), Total (Input),
    Allocation (GoldBorderDisplay).

    Posts typed messages upward to the owning screen.
    """

    DEFAULT_CSS = f"""
    HoldingTableRow {{
        layout: horizontal;
        height: 3;
        padding: 0 2;
    }}
    HoldingTableRow .hld-name {{
        width: 1fr;
        min-width: 16;
        height: 3;
    }}
    HoldingTableRow .hld-name-static {{
        width: 1fr;
        min-width: 16;
        height: 3;
        content-align: left middle;
        padding: 0 1;
        color: #aaaaaa;
    }}
    HoldingTableRow .hld-symbol {{
        width: 14;
        height: 3;
        margin-left: 1;
    }}
    HoldingTableRow .hld-symbol-static {{
        width: 14;
        height: 3;
        margin-left: 1;
        content-align: left middle;
        color: {TEXT_HINT};
        padding: 0 1;
    }}
    HoldingTableRow .hld-qty {{
        width: 14;
        height: 3;
        margin-left: 1;
    }}
    HoldingTableRow .hld-qty-static {{
        width: 14;
        height: 3;
        margin-left: 1;
        content-align: center middle;
        color: {TEXT_HINT};
    }}
    HoldingTableRow .hld-total {{
        width: 16;
        height: 3;
        margin-left: 1;
        content-align: right middle;
        color: #aaaaaa;
    }}
    HoldingTableRow .hld-total-input {{
        width: 16;
        height: 3;
        margin-left: 1;
    }}
    HoldingTableRow .alloc-display {{
        width: 14;
        height: 3;
        margin-left: 1;
        content-align: right middle;
    }}
    """

    class NameSubmitted(Message):
        """User submitted a modified name for an exact holding.

        Attributes:
            holding_id: Primary key.
            new_name: Updated display name.
        """

        def __init__(self, holding_id: int, new_name: str) -> None:
            """Store fields."""
            super().__init__()
            self.holding_id = holding_id
            self.new_name = new_name

    class QuantitySubmitted(Message):
        """User submitted a modified quantity for a listed holding.

        Attributes:
            holding_id: Primary key.
            raw_value: The raw Input string value (unparsed).
        """

        def __init__(self, holding_id: int, raw_value: str) -> None:
            """Store fields."""
            super().__init__()
            self.holding_id = holding_id
            self.raw_value = raw_value

    class TotalSubmitted(Message):
        """User submitted a modified total amount for an exact holding.

        Attributes:
            holding_id: Primary key.
            raw_value: The raw Input string value (unparsed).
        """

        def __init__(self, holding_id: int, raw_value: str) -> None:
            """Store fields."""
            super().__init__()
            self.holding_id = holding_id
            self.raw_value = raw_value

    def __init__(self, row: HoldingRowData) -> None:
        """Store holding data for compose."""
        super().__init__(id=f"hld-{row.holding_id}")
        self._row = row

    @property
    def holding_id(self) -> int:
        """Primary key of the holding this row represents."""
        return self._row.holding_id

    @property
    def holding_name(self) -> str:
        """Display name of the holding this row represents."""
        return self._row.name

    @property
    def unit_price(self) -> Decimal | None:
        """Cached unit price for listed holdings, or None for exact or unpriced."""
        return self._row.unit_price

    def compose(self) -> ComposeResult:
        """Render cells appropriate for the holding type."""
        cid = self._row.holding_id
        if self._row.holding_type == "listed":
            yield Static(self._row.name, classes="hld-name-static")
            yield Static(self._row.symbol or "", classes="hld-symbol-static")
            yield QuantityInput(
                value=QuantityInput.format(self._row.quantity),
                id=f"qty-{cid}",
                classes="hld-qty",
            )
            yield Static(MoneyInput.format(self._row.total, placeholder=""), classes="hld-total")
        else:
            yield TextInput(
                value=self._row.name,
                id=f"name-{cid}",
                classes="hld-name",
            )
            yield Static("—", classes="hld-symbol-static")
            yield Static("—", classes="hld-qty-static")
            yield MoneyInput(
                value=MoneyInput.format(self._row.total, placeholder=""),
                id=f"total-{cid}",
                classes="hld-total-input",
            )
        yield GoldBorderDisplay(
            f"{self._row.total_allocation_percent:.0f}%",
            id=f"alloc-{cid}",
            classes="alloc-display",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Post typed messages for each editable cell."""
        cid = self._row.holding_id
        input_id = event.input.id or ""
        event.stop()
        if input_id == f"name-{cid}":
            self.post_message(self.NameSubmitted(cid, event.value))
        elif input_id == f"qty-{cid}":
            self.post_message(self.QuantitySubmitted(cid, event.value))
        elif input_id == f"total-{cid}":
            self.post_message(self.TotalSubmitted(cid, event.value))


# ── _CashBalanceRow ───────────────────────────────────────────────────────────


class _CashBalanceRow(Horizontal):
    """Horizontal row for the uninvested cash balance field."""

    DEFAULT_CSS = """
    _CashBalanceRow {
        height: 3;
        padding: 0 2;
    }
    _CashBalanceRow .cbr-label {
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    _CashBalanceRow .cbr-input {
        width: 20;
        height: 3;
        margin-left: 1;
    }
    """

    def __init__(self, cash_balance: Decimal | None) -> None:
        """Store the initial balance value."""
        super().__init__()
        self._cash_balance = cash_balance

    def compose(self) -> ComposeResult:
        """Render the label and editable balance input."""
        yield Static("Uninvested Cash Balance", classes="cbr-label")
        yield MoneyInput(
            value=MoneyInput.format(self._cash_balance, placeholder=""),
            id="ie-cash-balance",
            classes="cbr-input",
        )


# ── _ColumnHeaders ────────────────────────────────────────────────────────────


class _ColumnHeaders(Horizontal):
    """Column header row for the holdings table."""

    DEFAULT_CSS = """
    _ColumnHeaders {
        height: 1;
        padding: 0 2;
        margin-top: 1;
    }
    _ColumnHeaders .ch-name {
        width: 1fr;
        min-width: 16;
        color: #ffffff;
        text-style: bold;
    }
    _ColumnHeaders .ch-symbol {
        width: 14;
        margin-left: 1;
        color: #ffffff;
        text-style: bold;
    }
    _ColumnHeaders .ch-qty {
        width: 14;
        margin-left: 1;
        color: #ffffff;
        text-style: bold;
    }
    _ColumnHeaders .ch-total {
        width: 16;
        margin-left: 1;
        color: #ffffff;
        text-style: bold;
    }
    _ColumnHeaders .ch-alloc {
        width: 14;
        margin-left: 1;
        color: #ffffff;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        """Render column header labels."""
        yield Static("Name", classes="ch-name")
        yield Static("Symbol", classes="ch-symbol")
        yield Static("Quantity", classes="ch-qty")
        yield Static("Total", classes="ch-total")
        yield Static("Allocation", classes="ch-alloc")


# ── InvestmentEditorScreen ────────────────────────────────────────────────────


class InvestmentEditorScreen(Screen[None]):
    """Investment Editor screen — Flow F-6.

    Displays the uninvested cash balance and all active holdings of an
    InvestmentAccount. Keyboard bindings for edit operations (F2, F6, F8) are
    stubbed until the corresponding dialogs (F-7a, F-7b) are implemented.

    Args:
        account_id: Primary key of the InvestmentAccount to display.
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("f2", "add_holding", "Add Holding", show=True),
        Binding("f6", "open_allocation", "Open", show=True),
        Binding("f8", "discard_holding", "Discard", show=True),
    ]

    DEFAULT_CSS = f"""
    InvestmentEditorScreen {{
        background: #000080;
    }}

    #ie-title-bar {{
        background: {PANEL_FILL};
        height: 3;
        border-bottom: solid #aaaaff;
        padding: 0 2;
    }}

    #ie-account-name {{
        color: #aaaaff;
        text-style: bold;
        width: 1fr;
        height: 3;
        content-align: left middle;
    }}

    #ie-date {{
        color: #aaaaaa;
        height: 3;
        content-align: right middle;
        width: 14;
    }}

    #ie-content {{
        background: #000080;
        padding: 1 1;
    }}

    .ie-section-label {{
        color: #aaaaff;
        text-style: bold;
        padding: 1 1 0 1;
        height: 2;
        content-align: left bottom;
    }}
    """

    def __init__(self, account_id: int) -> None:
        """Store the account ID to load on mount."""
        super().__init__()
        self._account_id = account_id
        self._cash_balance: Decimal | None = None
        self._holding_totals: dict[int, Decimal | None] = {}

    def compose(self) -> ComposeResult:
        """Render the title bar, loading area, total bar, and footer."""
        with Horizontal(id="ie-title-bar"):
            yield Static("", id="ie-account-name")
            yield Static("", id="ie-date")
        with VerticalScroll(id="ie-content", can_focus=False):
            yield LoadingIndicator()
        yield SummaryBar([("ie-total-label", "Total", "fill"), ("ie-total-amount", "", 20)])
        yield SplitFooter({"open_allocation", "discard_holding"})

    def on_mount(self) -> None:
        """Show the effective date and kick off the data-load worker."""
        self.query_one("#ie-date", Static).update(
            str(self.app.effective_date)  # type: ignore[attr-defined]
        )
        self.run_worker(self._load_data(), exclusive=True, name="load-ie")

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
        """Show F6/F8 only when the appropriate widget type is focused."""
        if action == "open_allocation":
            focused = self.focused
            return isinstance(focused, GoldBorderDisplay) and (focused.id or "").startswith(
                "alloc-"
            )
        if action == "discard_holding":
            focused = self.focused
            if focused is None:
                return False
            return isinstance(focused.parent, HoldingTableRow)
        return True

    def _refresh_total(self) -> None:
        """Recompute and display the account total from cached balances."""
        total = (self._cash_balance or Decimal("0")) + sum(
            (t for t in self._holding_totals.values() if t is not None),
            Decimal("0"),
        )
        self.query_one(SummaryBar).update_item("ie-total-amount", MoneyInput.format(total))

    # ── Cash balance input ────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """BS-OP-7: Parse and persist an updated uninvested cash balance."""
        if event.input.id != "ie-cash-balance":
            return
        event.stop()
        try:
            new_balance = MoneyInput.parse(event.value)
        except InvalidOperation:
            self.notify("Invalid balance — enter a numeric value.", severity="error", timeout=4)
            return
        self.run_worker(
            self._do_update_cash_balance(new_balance),
            exclusive=False,
            name="update-cash-balance",
        )

    # ── Messages from HoldingTableRow ─────────────────────────────────────

    def on_holding_table_row_name_submitted(self, event: HoldingTableRow.NameSubmitted) -> None:
        """Rename an exact holding; no reload required."""
        new_name = event.new_name.strip()
        if not new_name:
            self.notify("Name cannot be empty.", severity="error", timeout=3)
            return
        self.run_worker(
            self._do_update_holding_name(event.holding_id, new_name),
            exclusive=False,
            name=f"update-hld-name-{event.holding_id}",
        )

    def on_holding_table_row_quantity_submitted(
        self, event: HoldingTableRow.QuantitySubmitted
    ) -> None:
        """BS-OP-10: Parse quantity and persist; update the total cell in-place."""
        try:
            new_qty = QuantityInput.parse(event.raw_value)
        except InvalidOperation:
            self.notify("Invalid quantity — enter a numeric value.", severity="error", timeout=4)
            return
        if new_qty <= 0:
            self.notify("Quantity must be positive.", severity="error", timeout=4)
            return
        # Capture the unit price now so the worker can recompute the total without a
        # network round-trip. After session.commit() the transient price is gone.
        unit_price: Decimal | None = None
        try:
            unit_price = self.query_one(f"#hld-{event.holding_id}", HoldingTableRow).unit_price
        except Exception:
            pass
        self.run_worker(
            self._do_update_quantity(event.holding_id, new_qty, unit_price),
            exclusive=False,
            name=f"update-qty-{event.holding_id}",
        )

    def on_holding_table_row_total_submitted(self, event: HoldingTableRow.TotalSubmitted) -> None:
        """BS-OP-9: Parse the amount and persist; no reload required."""
        try:
            new_amount = MoneyInput.parse(event.raw_value)
        except InvalidOperation:
            self.notify("Invalid amount — enter a numeric value.", severity="error", timeout=4)
            return
        self.run_worker(
            self._do_update_exact_amount(event.holding_id, new_amount),
            exclusive=False,
            name=f"update-amount-{event.holding_id}",
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_go_back(self) -> None:
        """Return to BalanceSheetSummary (Esc)."""
        self.app.pop_screen()

    def action_add_holding(self) -> None:
        """Open AddHoldingDialog to add a new holding (F2 — BS-OP-8)."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        asset_classes = self.app.services.balance_sheet.get_asset_classes(as_of)  # type: ignore[attr-defined]

        # Snapshot the focused widget's id before the dialog steals focus so we can
        # restore it after the screen reloads on success.
        pre_dialog_focus_id: str | None = self.focused.id if self.focused else None

        def _on_created(holding_id: int | None) -> None:
            if holding_id is not None:
                self.run_worker(
                    self._load_data(focus_id=pre_dialog_focus_id),
                    exclusive=True,
                    name="reload-ie-after-add",
                )

        self.app.push_screen(
            AddHoldingDialog(self._account_id, asset_classes),
            callback=_on_created,
        )

    def action_open_allocation(self) -> None:
        """Open HoldingAllocationDialog for the focused row (F6 — F-7b)."""
        focused = self.focused
        if not isinstance(focused, GoldBorderDisplay):
            return
        fid = focused.id or ""
        if not fid.startswith("alloc-"):
            return
        try:
            holding_id = int(fid.removeprefix("alloc-"))
        except ValueError:
            return
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        asset_classes = self.app.services.balance_sheet.get_asset_classes(as_of)  # type: ignore[attr-defined]
        initial = self.app.services.balance_sheet.get_holding_allocations(holding_id, as_of)  # type: ignore[attr-defined]

        focused_ref = focused  # GoldBorderDisplay; narrowed by the isinstance check above

        def _on_saved(saved: bool | None) -> None:
            if saved:
                try:
                    focused_ref.update("100%")
                except Exception:
                    pass

        from personal_finance.ui.screens.balance_sheet_dialogs import (
            HoldingAllocationDialog,  # noqa: PLC0415
        )

        self.app.push_screen(
            HoldingAllocationDialog(holding_id, asset_classes, initial),
            callback=_on_saved,
        )

    def action_discard_holding(self) -> None:
        """Open ConfirmationDialog to discard the focused holding (F8 — BS-OP-11)."""
        focused = self.focused
        if focused is None:
            return
        parent = focused.parent
        if not isinstance(parent, HoldingTableRow):
            return
        holding_id = parent.holding_id
        holding_name = parent.holding_name

        def _on_confirmed(confirmed: bool | None) -> None:
            if confirmed:
                self.run_worker(
                    self._do_discard_holding(holding_id),
                    exclusive=False,
                    name=f"discard-hld-{holding_id}",
                )

        self.app.push_screen(
            ConfirmationDialog(f"Discard holding '{holding_name}'?"),
            callback=_on_confirmed,
        )

    # ── Workers ───────────────────────────────────────────────────────────────

    async def _do_discard_holding(self, holding_id: int) -> None:
        """BS-OP-11: Soft-delete the holding and remove its row from the screen."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.balance_sheet.discard_holding(  # type: ignore[attr-defined]
                holding_id, as_of
            )
            try:
                self.query_one(f"#hld-{holding_id}", HoldingTableRow).remove()
            except Exception:
                pass
            self._holding_totals.pop(holding_id, None)
            self._refresh_total()
        except Exception as exc:
            logger.error("discard_holding_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to discard holding: {exc}", severity="error", timeout=5)

    async def _do_update_exact_amount(self, holding_id: int, new_amount: Decimal) -> None:
        """Persist an exact holding amount (no reload — value already shown)."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.balance_sheet.update_holding_exact_amount(  # type: ignore[attr-defined]
                holding_id, as_of, new_amount
            )
            self._holding_totals[holding_id] = new_amount
            self._refresh_total()
        except Exception as exc:
            logger.error("update_holding_amount_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save amount: {exc}", severity="error", timeout=5)

    async def _do_update_holding_name(self, holding_id: int, new_name: str) -> None:
        """Persist a holding name change (no reload — value already shown)."""
        try:
            self.app.services.balance_sheet.update_holding_name(  # type: ignore[attr-defined]
                holding_id, new_name
            )
        except Exception as exc:
            logger.error("update_holding_name_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save name: {exc}", severity="error", timeout=5)

    async def _do_update_cash_balance(self, new_balance: Decimal) -> None:
        """Persist the uninvested cash balance (no reload — value already shown)."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.balance_sheet.update_uninvested_cash_balance(  # type: ignore[attr-defined]
                self._account_id, as_of, new_balance
            )
            self._cash_balance = new_balance
            self._refresh_total()
        except Exception as exc:
            logger.error("update_cash_balance_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save cash balance: {exc}", severity="error", timeout=5)

    async def _do_update_quantity(
        self, holding_id: int, new_qty: Decimal, unit_price: Decimal | None
    ) -> None:
        """Persist a quantity change and update the total cell in-place.

        Uses the unit price captured before the commit rather than triggering a
        full reload. After session.commit() SQLAlchemy expires the in-memory
        instance and the transient unit price is lost; the cached value avoids a
        network round-trip to the quote service.
        """
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            self.app.services.balance_sheet.update_holding_listed_quantity(  # type: ignore[attr-defined]
                holding_id, as_of, new_qty
            )
            if unit_price is not None:
                new_total = unit_price * new_qty
                self._holding_totals[holding_id] = new_total
                try:
                    row = self.query_one(f"#hld-{holding_id}", HoldingTableRow)
                    row.query_one(".hld-total", Static).update(MoneyInput.format(new_total))
                except Exception:
                    pass
                self._refresh_total()
        except Exception as exc:
            logger.error("update_holding_quantity_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save quantity: {exc}", severity="error", timeout=5)

    async def _load_data(self, *, focus_id: str | None = None) -> None:
        """Load investment details and populate the screen.

        Args:
            focus_id: Widget id to restore focus to after mounting.  When
                ``None`` (initial load) the first ``Input`` receives focus.
        """
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            details: InvestmentDetails = (
                await self.app.services.balance_sheet.get_investment_details(  # type: ignore[attr-defined]
                    self._account_id, as_of
                )
            )
            self.query_one("#ie-account-name", Static).update(details.account_name)
            self._cash_balance = details.cash_balance
            self._holding_totals = {r.holding_id: r.total for r in details.holdings}
            self._refresh_total()
            content = self.query_one("#ie-content", VerticalScroll)
            await content.remove_children()
            await content.mount(*_build_content_widgets(details))
            try:
                if focus_id:
                    content.query_one(f"#{focus_id}").focus()
                else:
                    content.query("Input").first(Input).focus()
            except Exception:
                try:
                    content.query("Input").first(Input).focus()
                except Exception:
                    pass
        except Exception as exc:
            logger.error("investment_editor_load_failed", error=str(exc), exc_info=True)
            content = self.query_one("#ie-content", VerticalScroll)
            await content.remove_children()
            await content.mount(Static(f"Error loading investment details: {exc}"))


# ── Module-level helpers ──────────────────────────────────────────────────────


def _build_content_widgets(details: InvestmentDetails) -> list[Widget]:
    """Build the ordered list of widgets to mount into the investment editor scroll area.

    Args:
        details: Populated investment account details.

    Returns:
        Flat list of widgets ready to pass to ``VerticalScroll.mount()``.
    """
    widgets: list[Widget] = []
    widgets.append(_CashBalanceRow(details.cash_balance))
    widgets.append(Static("Holdings", classes="ie-section-label"))
    widgets.append(_ColumnHeaders())
    for row in details.holdings:
        widgets.append(HoldingTableRow(row))
    return widgets
