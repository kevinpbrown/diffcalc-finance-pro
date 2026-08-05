"""General core service — GEN-OP domain operations spanning multiple modules."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from personal_finance.service.core.balance_sheet_service import BalanceSheetService
from personal_finance.service.core.goal_service import GoalService


class GeneralService:
    """Domain operations that aggregate across Balance Sheet and Goals data.

    Implements cross-cutting operations (``GEN-OP-*`` in the service-operations
    spec) that draw on data from more than one domain submodule.

    Args:
        balance_sheet: Core service for balance sheet queries.
        goals: Core service for goal queries.
        cushion: Dollar amount reserved as a buffer against the available
            investment cash (read from TOML config key
            ``settings.amount_left_to_invest_cushion``).
    """

    def __init__(
        self,
        balance_sheet: BalanceSheetService,
        goals: GoalService,
        cushion: Decimal,
    ) -> None:
        """Store injected services and cushion."""
        self._balance_sheet = balance_sheet
        self._goals = goals
        self._cushion = cushion

    async def get_amount_left_to_invest(self, session: Session, as_of: date) -> Decimal:
        """GEN-OP-1: Return the cash available for new long-term investments.

        Pricing is no longer pre-swept via ``list_all_accounts``:
        ``GoalService.get_total_bank_claim`` prices exactly the AutoFill goals'
        allocated accounts it needs, backed by a cache at the ``QuoteService``
        layer, so this composite operation no longer depends on a shared
        session identity map to keep pricing consistent across its calls.

        Formula:
            Σ(BANK account balances)
          - Σ(current liability balances)
          - Σ(goal bank-portion claims)
          - cushion

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for all balance and active-state lookups.

        Returns:
            Net investable cash as a ``Decimal``. Can be negative if liabilities
            or goal claims exceed bank balances.
        """
        bank_total = self._balance_sheet.get_total_bank_balance(session, as_of)
        liability_total = self._balance_sheet.get_total_current_liability_balance(session, as_of)
        goal_claims = await self._goals.get_total_bank_claim(session, as_of)
        return bank_total - liability_total - goal_claims - self._cushion
