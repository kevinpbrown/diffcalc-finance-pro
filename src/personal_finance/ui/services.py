"""Service container for the UI layer.

Holds a reference to every service instance the UI needs. Screens access
services via ``self.app.services`` rather than instantiating them directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from personal_finance.service.application.balance_sheet_app_service import BalanceSheetAppService
from personal_finance.service.application.cash_flow_app_service import CashFlowAppService
from personal_finance.service.application.dashboard_service import DashboardService
from personal_finance.service.application.goal_app_service import GoalAppService


@dataclass(frozen=True)
class Services:
    """Immutable container of all service instances.

    Attributes:
        dashboard: GEN-OP service for the Dashboard screen.
        balance_sheet: BFF service for the Balance Sheet Summary screen.
        goals: BFF service for the Goals screens.
        cash_flow: BFF service for the Cash Flow screens.
    """

    dashboard: DashboardService
    balance_sheet: BalanceSheetAppService
    goals: GoalAppService
    cash_flow: CashFlowAppService
