"""Domain layer: business logic, ORM models, and domain invariants.

Shared entities (EffectiveAmount, Person, AccountAssetClass) live in this package root.
Feature-specific models live in the balance_sheet, goals, and cash_flow submodules.
"""

from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.base import Base
from personal_finance.domain.cash_flow import (
    AutomatedContribution,
    HouseholdExpense,
    HouseholdExpenseClassification,
    HouseholdExpenseFrequency,
    HouseholdExpenseSource,
    PersonalCashFlowProfile,
)
from personal_finance.domain.effective_amount import (
    EffectiveAmount,
    EffectiveAmountEntry,
    EffectiveAmountEntrySource,
)
from personal_finance.domain.person import Person

__all__ = [
    "AccountAssetClass",
    "AutomatedContribution",
    "Base",
    "EffectiveAmount",
    "EffectiveAmountEntry",
    "EffectiveAmountEntrySource",
    "HouseholdExpense",
    "HouseholdExpenseClassification",
    "HouseholdExpenseFrequency",
    "HouseholdExpenseSource",
    "Person",
    "PersonalCashFlowProfile",
]
