"""PersonalFinanceApp — the Textual application root.

Owns the SQLAlchemy engine and session lifecycle, constructs the Services
container, and drives the startup sequence (Splash → Dashboard).
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy.engine import Engine
from textual.app import App

from personal_finance import __version__
from personal_finance.db import (
    backup_database,
    create_db_engine,
    create_session_factory,
    initialize_database,
    load_config,
)
from personal_finance.integrations.caching_quote_service import CachingQuoteService
from personal_finance.integrations.yahoo_finance import YahooFinanceQuoteService
from personal_finance.service.application.balance_sheet_app_service import BalanceSheetAppService
from personal_finance.service.application.cash_flow_app_service import CashFlowAppService
from personal_finance.service.application.dashboard_service import DashboardService
from personal_finance.service.application.goal_app_service import GoalAppService
from personal_finance.service.core.balance_sheet_service import BalanceSheetService
from personal_finance.service.core.cash_flow_service import CashFlowService
from personal_finance.service.core.general_service import GeneralService
from personal_finance.service.core.goal_service import GoalService
from personal_finance.ui.screens.dashboard import DashboardScreen
from personal_finance.ui.screens.splash import SplashScreen
from personal_finance.ui.services import Services

logger = structlog.get_logger(__name__)


class PersonalFinanceApp(App[None]):
    """Root Textual application for Personal Finance.

    Owns:
    - The SQLAlchemy engine and session factory (created during startup).
      Sessions are opened per application-service call
      (session-per-application-operation), not held for the app's lifetime.
    - The ``Services`` container, accessible to all screens via
      ``self.app.services``.
    - The global ``effective_date`` used across all module screens.
    """

    CSS_PATH = "netware.tcss"
    TITLE = f"Personal Finance v{__version__}"
    ENABLE_COMMAND_PALETTE = False

    # Populated during startup worker; None until init completes.
    services: Services | None = None
    effective_date: date = date.today()

    _MIN_SPLASH_SECONDS = 3.0

    def __init__(self) -> None:
        """Set up internal state before any screens are composed."""
        super().__init__()
        self._engine: Engine | None = None
        self._splash: SplashScreen | None = None

    # ── Application lifecycle ──────────────────────────────────────────────

    def on_mount(self) -> None:
        """Push the splash screen and start the background init worker."""
        splash = SplashScreen()
        self._splash = splash
        self.push_screen(splash)
        self.run_worker(self._startup(), exclusive=True, name="startup")

    async def _startup(self) -> None:
        """Background worker: load config, init DB, wire services, go to Dashboard."""
        start = time.monotonic()

        def status(msg: str) -> None:
            if self._splash is not None:
                self._splash.set_status(msg)

        try:
            status("Loading configuration…")
            config = load_config()

            status("Backing up database…")
            backup_database()

            status("Connecting to database…")
            engine = create_db_engine()
            self._engine = engine

            status("Initializing schema and seed data…")
            initialize_database(engine, config)

            status("Wiring services…")
            session_factory = create_session_factory(engine)

            cushion = Decimal(str(config["settings"]["amount_left_to_invest_cushion"]))
            same_day_quote_ttl_seconds = float(config["settings"]["same_day_quote_ttl_seconds"])
            quote_service = CachingQuoteService(
                YahooFinanceQuoteService(), same_day_ttl_seconds=same_day_quote_ttl_seconds
            )

            balance_sheet_svc = BalanceSheetService(quote_service)
            goal_svc = GoalService(balance_sheet_svc)
            cash_flow_svc = CashFlowService()
            general_svc = GeneralService(balance_sheet_svc, goal_svc, cushion)

            balance_sheet_app_svc = BalanceSheetAppService(balance_sheet_svc, session_factory)
            self.services = Services(
                dashboard=DashboardService(general_svc, balance_sheet_app_svc, session_factory),
                balance_sheet=balance_sheet_app_svc,
                goals=GoalAppService(goal_svc, balance_sheet_svc, session_factory),
                cash_flow=CashFlowAppService(cash_flow_svc, goal_svc, session_factory),
            )

            status("Ready.")
            logger.info("startup_complete")

            # Hold the splash for a minimum duration, but allow Enter to skip it.
            remaining = self._MIN_SPLASH_SECONDS - (time.monotonic() - start)
            splash = self._splash
            if remaining > 0 and splash is not None:
                try:
                    await asyncio.wait_for(splash._skip_event.wait(), timeout=remaining)
                except TimeoutError:
                    pass

            self._splash = None
            self.switch_screen(DashboardScreen())

        except Exception as exc:  # noqa: BLE001
            logger.error("startup_failed", error=str(exc), exc_info=True)
            status(f"Startup failed: {exc}")
            # Leave the splash on screen so the user sees the error.

    # ── Cleanup ────────────────────────────────────────────────────────────

    async def on_unmount(self) -> None:
        """Dispose the SQLAlchemy engine on exit."""
        if self._engine is not None:
            self._engine.dispose()
