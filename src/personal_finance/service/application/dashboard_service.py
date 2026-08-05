"""Dashboard application service — screen-level facade for the Dashboard."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from personal_finance.db import transaction
from personal_finance.service.application.balance_sheet_app_service import BalanceSheetAppService
from personal_finance.service.core.general_service import GeneralService


@dataclass(frozen=True)
class DashboardSummary:
    """DTO for the Dashboard summary panel.

    Attributes:
        amount_left: Cash available for new long-term investments (GEN-OP-1).
        current_net_worth: Current assets minus current liabilities.
        total_net_worth: All assets minus all liabilities.
    """

    amount_left: Decimal
    current_net_worth: Decimal
    total_net_worth: Decimal


class DashboardService:
    """Application service for the Dashboard screen.

    Thin facade over ``GeneralService`` and ``BalanceSheetAppService``. Exists
    to enforce the rule that UI screens import only from ``service/application/``,
    never directly from ``service/core/``.

    Owns the session lifetime for its own core-service calls
    (session-per-application-operation): each method opens one session via
    ``db.transaction()`` for calls into ``GeneralService``. The call into
    ``BalanceSheetAppService.get_summary`` manages its own independent session
    internally, since it is itself a public application-service method.

    Args:
        general: The injected GeneralService instance.
        balance_sheet: The injected BalanceSheetAppService instance.
        session_factory: Session factory used to open a session for calls into
            ``GeneralService``.
    """

    def __init__(
        self,
        general: GeneralService,
        balance_sheet: BalanceSheetAppService,
        session_factory: sessionmaker[Session],
    ) -> None:
        """Store injected services and session factory."""
        self._general = general
        self._balance_sheet = balance_sheet
        self._session_factory = session_factory

    async def get_amount_left_to_invest(self, as_of: date) -> Decimal:
        """GEN-OP-1: Delegate to GeneralService.

        Args:
            as_of: Effective date for all balance and active-state lookups.

        Returns:
            Net investable cash as a ``Decimal``.
        """
        with transaction(self._session_factory) as session:
            return await self._general.get_amount_left_to_invest(session, as_of)

    async def get_summary(self, as_of: date) -> DashboardSummary:
        """Return all dashboard metrics without duplicating net worth logic.

        Delegates net worth values to ``BalanceSheetAppService.get_summary``,
        which is the single canonical source for that calculation. Pricing
        consistency between this call and that one is provided by the
        cache-backed ``QuoteService``, not by sharing a session/identity map —
        the two calls use independent sessions.

        Args:
            as_of: Effective date for all balance and active-state lookups.

        Returns:
            ``DashboardSummary`` with amount_left, current_net_worth, and total_net_worth.
        """
        with transaction(self._session_factory) as session:
            amount_left = await self._general.get_amount_left_to_invest(session, as_of)
        bs = await self._balance_sheet.get_summary(as_of)
        return DashboardSummary(
            amount_left=amount_left,
            current_net_worth=bs.current_net_worth,
            total_net_worth=bs.total_net_worth,
        )
