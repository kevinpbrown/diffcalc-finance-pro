"""Dashboard screen — Flow F-3.

Houses the global Session Effective Date, a financial summary panel, and the
top-level navigation menu.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import structlog
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Rule, Static

from personal_finance.service.application.dashboard_service import DashboardSummary
from personal_finance.ui.palette import PANEL_FILL
from personal_finance.ui.screens.dialogs import ConfirmationDialog
from personal_finance.ui.widgets.date_input import DateInput

logger = structlog.get_logger(__name__)

_PENDING = "Calculating…"


class DashboardScreen(Screen[None]):
    """Dashboard — the top-level navigation screen (Flow F-3).

    Hosts the Session Effective Date field, a bordered summary panel showing
    Amount Left to Invest, Current Net Worth, and Total Net Worth, and the
    navigation menu.  The effective date is stored as a ``reactive`` on the App
    so all module screens can observe it.
    """

    BINDINGS = [
        Binding("escape", "request_quit", "Quit", show=True),
        Binding("q", "request_quit", "Quit", show=False),
        Binding("f5", "refresh_dashboard", "Refresh", show=True),
    ]

    DEFAULT_CSS = f"""
    DashboardScreen {{
        align: center top;
        background: #0000aa;
    }}

    #dash-inner {{
        width: 60;
        height: auto;
        margin-top: 3;
    }}

    #dash-fields {{
        width: 60;
        height: auto;
        margin-bottom: 1;
    }}

    .dash-row {{
        height: 3;
        width: 60;
        layout: horizontal;
    }}

    .dash-row Label {{
        width: 28;
        height: 3;
        content-align: right middle;
        color: #aaaaaa;
    }}

    .dash-row DateInput {{
        width: 18;
        margin-left: 4;
        height: 3;
    }}

    #stats-container {{
        width: 48;
        height: auto;
        border: solid #ffffff;
        background: {PANEL_FILL};
        padding: 1 0;
        margin-left: 6;
        margin-bottom: 1;
    }}

    .stat-row {{
        height: 1;
        width: 100%;
        layout: horizontal;
    }}

    .stat-label {{
        width: 28;
        height: 1;
        content-align: left middle;
        color: #aaaaaa;
    }}

    .stat-value {{
        width: 18;
        height: 1;
        content-align: right middle;
        color: #ffffff;
    }}

    #menu-container {{
        width: 54;
        height: auto;
        border: solid #ffffff;
        background: {PANEL_FILL};
        padding: 0;
        margin-left: 3;
    }}

    #menu-title {{
        width: 100%;
        text-align: center;
        color: #ffffff;
        text-style: bold;
        height: 1;
        padding: 0 1;
    }}

    #menu-container Rule {{
        color: #ffffff;
        margin: 0;
        height: 1;
    }}

    #menu-list {{
        width: 100%;
        height: auto;
        border: none;
        background: {PANEL_FILL};
        padding: 0 1;
        scrollbar-size-vertical: 0;
    }}

    #menu-list > ListItem {{
        background: {PANEL_FILL};
        color: #ffffff;
        text-style: bold;
        height: 1;
        padding: 0;
    }}

    #menu-list > ListItem.-highlight {{
        background: {PANEL_FILL};
        color: #ffffff;
        text-style: bold;
    }}

    #menu-list:focus > ListItem.-highlight {{
        background: #000080;
        color: #ffffff;
    }}
    """

    def __init__(self) -> None:
        """Initialise with today as the default effective date."""
        super().__init__()
        self._effective_date: date = date.today()

    def compose(self) -> ComposeResult:
        """Render the dashboard layout."""
        with Container(id="dash-inner"):
            with Vertical(id="dash-fields"):
                with Container(classes="dash-row"):
                    yield Label("Session Effective Date:")
                    yield DateInput(
                        value=self._effective_date,
                        id="effective-date",
                    )
            with Vertical(id="stats-container"):
                with Container(classes="stat-row"):
                    yield Label("Amount Left to Invest:", classes="stat-label")
                    yield Static(_PENDING, id="amount-left", classes="stat-value")
                with Container(classes="stat-row"):
                    yield Label("Current Net Worth:", classes="stat-label")
                    yield Static(_PENDING, id="current-net-worth", classes="stat-value")
                with Container(classes="stat-row"):
                    yield Label("Total Net Worth:", classes="stat-label")
                    yield Static(_PENDING, id="total-net-worth", classes="stat-value")
            with Vertical(id="menu-container"):
                yield Static("Available Options", id="menu-title")
                yield Rule()
                with ListView(id="menu-list"):
                    yield ListItem(Label("Balance Sheet"), id="menu-balance-sheet")
                    yield ListItem(Label("Goals"), id="menu-goals")
                    yield ListItem(Label("Cash Flow"), id="menu-cash-flow")
                    yield ListItem(Label("Quit"), id="menu-quit")
        yield Footer()

    def on_mount(self) -> None:
        """Load the initial dashboard statistics and focus the effective-date field."""
        self._refresh_stats(self._effective_date)
        self.query_one("#effective-date", DateInput).focus()

    def on_screen_resume(self) -> None:
        """Refresh dashboard statistics when returning to the dashboard."""
        self._refresh_stats(self._effective_date)

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        """Up/Down navigate to/from the menu; ListView handles internal navigation."""
        if isinstance(self.focused, ListView):
            return
        if event.key == "down":
            self.focus_next()
            event.stop()
        elif event.key == "up":
            self.focus_previous()
            event.stop()

    def on_date_input_date_changed(self, event: DateInput.DateChanged) -> None:
        """React to a new Session Effective Date."""
        self._effective_date = event.value
        self.app.effective_date = event.value  # type: ignore[attr-defined]
        self._refresh_stats(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle navigation menu selections."""
        item_id = event.item.id
        if item_id == "menu-quit":
            self.action_request_quit()
        elif item_id == "menu-balance-sheet":
            from personal_finance.ui.screens.balance_sheet import (
                BalanceSheetScreen,  # noqa: PLC0415
            )

            self.app.push_screen(BalanceSheetScreen())
        elif item_id == "menu-goals":
            from personal_finance.ui.screens.goals import GoalsListScreen  # noqa: PLC0415

            self.app.push_screen(GoalsListScreen())
        elif item_id == "menu-cash-flow":
            from personal_finance.ui.screens.cash_flow import (  # noqa: PLC0415
                CashFlowPersonProfileView,
            )

            self.app.push_screen(CashFlowPersonProfileView())

    def action_request_quit(self) -> None:
        """Show a confirmation dialog; exit only if the user confirms.

        Uses push_screen with a callback rather than push_screen_wait because
        Textual 8.x requires push_screen_wait to run inside a worker, but
        action handlers run in the event-dispatch loop.
        """

        def _on_dismiss(confirmed: bool | None) -> None:
            if confirmed:
                self.app.exit()

        self.app.push_screen(ConfirmationDialog("Quit DiffCalc Finance Pro?"), callback=_on_dismiss)

    def action_refresh_dashboard(self) -> None:
        """F5: recompute the dashboard statistics for the current effective date."""
        self._refresh_stats(self._effective_date)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _refresh_stats(self, as_of: date) -> None:
        """Kick off a worker to recompute all dashboard statistics."""
        for widget_id in ("#amount-left", "#current-net-worth", "#total-net-worth"):
            self.query_one(widget_id, Static).update(_PENDING)
        self.run_worker(
            self._compute_stats(as_of),
            exclusive=True,
            name="compute-stats",
        )

    async def _compute_stats(self, as_of: date) -> None:
        """Background task: call GEN-OP-2 and update all dashboard statistics."""
        try:
            services = self.app.services  # type: ignore[attr-defined]
            summary: DashboardSummary = await services.dashboard.get_summary(as_of)

            def _fmt(v: Decimal) -> str:
                return f"$ {v:>13,.2f}"

            self.query_one("#amount-left", Static).update(_fmt(summary.amount_left))
            self.query_one("#current-net-worth", Static).update(_fmt(summary.current_net_worth))
            self.query_one("#total-net-worth", Static).update(_fmt(summary.total_net_worth))
        except Exception as exc:  # noqa: BLE001
            logger.error("dashboard_stats_failed", error=str(exc), exc_info=True)
            for widget_id in ("#amount-left", "#current-net-worth", "#total-net-worth"):
                self.query_one(widget_id, Static).update("—")
