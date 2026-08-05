"""Seed the database with a full sample household that exercises every feature.

Idempotent per module: each ``seed_*`` function skips its work if its table is
already populated, so the script can be re-run safely.

Usage (from project root):
    .venv/bin/python scripts/seed_sample_data.py

The script first runs the standard ``initialize_database`` (config seeds:
persons, asset classes, cash-flow profiles), backdates the seeded asset classes
to the sample effective date, then layers on the balance sheet, goals and cash
flow data.

The household
─────────────
Mom and Dad, one child. Everything is effective 2026-07-02 and deliberately
round — this is sample data for an article, not a sanitised real household.

Balance sheet
  Current assets       Joint Chequing $10,000, Joint Savings $40,000,
                       Emergency Fund GIC $30,000 (3.00% 1-year cashable)
  Long-term assets     Home $800,000, Mom's CR-V $40,000, Dad's Camry $35,000,
                       five investment accounts (RRSP/TFSA ×2, group RRSP) and
                       the child's RESP, all holding BMO and iShares ETFs
  Current liabilities  Mom's Visa $2,000, Dad's MasterCard $1,500
  Long-term            Mortgage $200,000

Goals
  Rainy day    Manual $45,000   AutoFill bank → Emergency Fund GIC
  Vacation     Manual $20,000   AutoFill bank → (no accounts)
  New vehicle  PV FV=$50,000 2026-07-02 → 2031-07-02 @ 4%, scalar bank $10,000
  Education    PV FV=$100,000 2021-01-01 → 2040-01-01 @ 5%, scalar bank $10,000
                                                     → Child's RESP (in surplus)
  Retirement   No target        scalar bank $0       → both RRSPs, both TFSAs,
                                                       Dad's group RRSP

  Total bank claims are $55,000 against $50,000 of bank balances, so the Goals
  screen shows its $5,000 overclaim warning.

Cash flow
  Mom      $140,000 gross / $98,000 net, $15,000 gross bonus, no RRSP match
  Dad      $110,000 gross / $76,000 net, 5% auto RRSP ($5,500) matched 5%
           ($5,500), both targeting the Retirement goal via his group RRSP
  Expenses $6,000/month across HOME / AUTO / OTHER and every source ×
           frequency combination
  Auto     $4,500/month of automated contributions, leaving $4,000/month
           retained
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from personal_finance.db import create_db_engine, get_db_path, initialize_database, load_config
from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet.account import (
    Account,
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.balance_sheet.holding import (
    HoldingAssetClassAllocation,
    ExactHolding,
    InvestmentAccountHolding,
    ListedSecurityHolding,
)
from personal_finance.domain.cash_flow.contribution import AutomatedContribution
from personal_finance.domain.cash_flow.expense import (
    HouseholdExpense,
    HouseholdExpenseClassification,
    HouseholdExpenseFrequency,
    HouseholdExpenseSource,
)
from personal_finance.domain.cash_flow.profile import PersonalCashFlowProfile
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.goals.goal import (
    Goal,
    GoalAssetClassTarget,
    GoalBankPortion,
    GoalBankPortionAutoFill,
    GoalBankPortionScalar,
    GoalValue,
    NoGoalValue,
    ScalarGoalValue,
    SimplePVGoalValue,
)
from personal_finance.domain.person import Person

_SEED_DATE = date(2026, 7, 2)

# Shorthands for the enums, purely to keep the data tables below readable.
_ASSET_CUR = AccountClassification.ASSET_CURRENT
_ASSET_LT = AccountClassification.ASSET_LONG_TERM
_LIAB_CUR = AccountClassification.LIABILITY_CURRENT
_LIAB_LT = AccountClassification.LIABILITY_LONG_TERM

_HOME = HouseholdExpenseClassification.HOME
_AUTO = HouseholdExpenseClassification.AUTO
_OTHER = HouseholdExpenseClassification.OTHER
_BANK_PAID = HouseholdExpenseSource.BANK
_CREDIT_PAID = HouseholdExpenseSource.CREDIT
_OTHER_PAID = HouseholdExpenseSource.OTHER
_REGULAR = HouseholdExpenseFrequency.REGULAR
_IRREGULAR = HouseholdExpenseFrequency.IRREGULAR


# ── Security reference data ───────────────────────────────────────────────────
# Symbol → (display name, asset class allocation summing to 100%). The couple
# holds only Canadian-listed BMO and iShares index ETFs — no individual stocks.
# The broad EAFE and asset-allocation funds are split across several classes,
# which is what makes the goal allocation screens interesting.
_ETFS: dict[str, tuple[str, dict[str, Decimal]]] = {
    "ZAG.TO": (
        "BMO Aggregate Bond Index ETF",
        {"Fixed Income": Decimal("100")},
    ),
    "XBB.TO": (
        "iShares Core Canadian Universe Bond Index ETF",
        {"Fixed Income": Decimal("100")},
    ),
    "ZCN.TO": (
        "BMO S&P/TSX Capped Composite Index ETF",
        {"Canadian Equity": Decimal("100")},
    ),
    "XIC.TO": (
        "iShares Core S&P/TSX Capped Composite Index ETF",
        {"Canadian Equity": Decimal("100")},
    ),
    "ZSP.TO": (
        "BMO S&P 500 Index ETF",
        {"US Equity": Decimal("100")},
    ),
    "XUU.TO": (
        "iShares Core S&P U.S. Total Market Index ETF",
        {"US Equity": Decimal("100")},
    ),
    "ZEA.TO": (
        "BMO MSCI EAFE Index ETF",
        {"European Equity": Decimal("65"), "APAC Equity": Decimal("35")},
    ),
    "XEF.TO": (
        "iShares Core MSCI EAFE IMI Index ETF",
        {"European Equity": Decimal("65"), "APAC Equity": Decimal("35")},
    ),
    "ZEM.TO": (
        "BMO MSCI Emerging Markets Index ETF",
        {"Emerging Equity": Decimal("100")},
    ),
    "XEC.TO": (
        "iShares Core MSCI Emerging Markets IMI Index ETF",
        {"Emerging Equity": Decimal("100")},
    ),
    "ZRE.TO": (
        "BMO Equal Weight REITs Index ETF",
        {"Other": Decimal("100")},
    ),
    "ZBAL.TO": (
        "BMO Balanced ETF",
        {
            "Fixed Income": Decimal("40"),
            "US Equity": Decimal("22"),
            "Canadian Equity": Decimal("18"),
            "European Equity": Decimal("10"),
            "APAC Equity": Decimal("5"),
            "Emerging Equity": Decimal("5"),
        },
    ),
}


# ── Construction helpers ──────────────────────────────────────────────────────


def _ea(amount: Decimal) -> EffectiveAmount:
    """Return a fresh timeline holding a single entry effective on the seed date."""
    timeline = EffectiveAmount()
    timeline.offer_value(_SEED_DATE, amount)
    return timeline


def _simple(
    session: Session,
    owners: list[Person],
    name: str,
    classification: AccountClassification,
    category: SimpleAccountCategory,
    balance: Decimal,
) -> SimpleAccount:
    acct = SimpleAccount(
        name=name,
        date_created=_SEED_DATE,
        date_effective=_SEED_DATE,
        date_modified=_SEED_DATE,
        classification=classification,
        owners=owners,
        type=category,
        balance=_ea(balance),
    )
    session.add(acct)
    return acct


def _investment(
    session: Session,
    owners: list[Person],
    name: str,
    classification: AccountClassification,
    registration: InvestmentRegistration,
    cash_balance: Decimal = Decimal("0"),
) -> InvestmentAccount:
    acct = InvestmentAccount(
        name=name,
        date_created=_SEED_DATE,
        date_effective=_SEED_DATE,
        date_modified=_SEED_DATE,
        classification=classification,
        owners=owners,
        investment_registration=registration,
        cash_balance=_ea(cash_balance),
    )
    session.add(acct)
    return acct


def _allocate(
    session: Session,
    holding: InvestmentAccountHolding,
    asset_classes: dict[str, AccountAssetClass],
    shares: dict[str, Decimal],
) -> None:
    """Attach asset class allocations, which must sum to exactly 100%."""
    total = sum(shares.values(), Decimal("0"))
    if total != Decimal("100"):
        raise ValueError(f"Allocations for {holding.name!r} sum to {total}%, not 100%.")
    for name, pct in shares.items():
        session.add(HoldingAssetClassAllocation(
            holding=holding,
            asset_class=asset_classes[name],
            percent_allocated=pct,
            date_created=_SEED_DATE,
            date_effective=_SEED_DATE,
            date_modified=_SEED_DATE,
        ))


def _exact(
    session: Session,
    account: InvestmentAccount,
    asset_classes: dict[str, AccountAssetClass],
    name: str,
    amount: Decimal,
    shares: dict[str, Decimal],
) -> ExactHolding:
    """Add a manually-valued holding (GIC, group plan fund) to ``account``."""
    holding = ExactHolding(
        name=name,
        date_created=_SEED_DATE,
        date_effective=_SEED_DATE,
        date_modified=_SEED_DATE,
        investment_account=account,
        amount=_ea(amount),
    )
    session.add(holding)
    _allocate(session, holding, asset_classes, shares)
    return holding


def _listed(
    session: Session,
    account: InvestmentAccount,
    asset_classes: dict[str, AccountAssetClass],
    symbol: str,
    quantity: int,
) -> ListedSecurityHolding:
    """Add a market-priced ETF holding to ``account``, looked up from ``_ETFS``."""
    display_name, shares = _ETFS[symbol]
    holding = ListedSecurityHolding(
        name=display_name,
        symbol=symbol,
        date_created=_SEED_DATE,
        date_effective=_SEED_DATE,
        date_modified=_SEED_DATE,
        investment_account=account,
        quantity=_ea(Decimal(quantity)),
    )
    session.add(holding)
    _allocate(session, holding, asset_classes, shares)
    return holding


def _goal(
    session: Session,
    name: str,
    goal_value: GoalValue,
    bank_portion: GoalBankPortion,
    asset_classes: dict[str, AccountAssetClass],
    targets: dict[str, Decimal],
    accounts: list[InvestmentAccount] | None = None,
) -> Goal:
    goal = Goal(
        name=name,
        date_created=_SEED_DATE,
        date_effective=_SEED_DATE,
        date_modified=_SEED_DATE,
        goal_value=goal_value,
        bank_portion=bank_portion,
    )
    for account in accounts or []:
        goal.allocated_accounts.append(account)
    for class_name, percent in targets.items():
        session.add(GoalAssetClassTarget(
            goal=goal,
            asset_class=asset_classes[class_name],
            target_percent=percent,
            date_created=_SEED_DATE,
            date_effective=_SEED_DATE,
            date_modified=_SEED_DATE,
        ))
    session.add(goal)
    return goal


def _scalar_value(amount: Decimal) -> ScalarGoalValue:
    return ScalarGoalValue(value=_ea(amount))


def _scalar_bank(amount: Decimal) -> GoalBankPortionScalar:
    return GoalBankPortionScalar(amount=_ea(amount))


def _expense(
    session: Session,
    name: str,
    monthly: Decimal,
    classification: HouseholdExpenseClassification,
    source: HouseholdExpenseSource,
    frequency: HouseholdExpenseFrequency,
) -> HouseholdExpense:
    expense = HouseholdExpense(
        name=name,
        date_created=_SEED_DATE,
        date_effective=_SEED_DATE,
        date_modified=_SEED_DATE,
        amount=_ea(monthly),
        classification=classification,
        source=source,
        frequency=frequency,
    )
    session.add(expense)
    return expense


def _contribution(
    session: Session,
    name: str,
    monthly: Decimal,
    source_account: Account,
    destination_account: Account,
    target_goal: Goal,
) -> AutomatedContribution:
    contribution = AutomatedContribution(
        name=name,
        date_created=_SEED_DATE,
        date_effective=_SEED_DATE,
        date_modified=_SEED_DATE,
        amount=_ea(monthly),
        source_account=source_account,
        destination_account=destination_account,
        target_goal=target_goal,
    )
    session.add(contribution)
    return contribution


# ── Seed steps ────────────────────────────────────────────────────────────────


def backdate_asset_classes(session: Session) -> None:
    """Pull asset class ``date_created`` back to the seed date.

    ``initialize_database`` stamps config-seeded asset classes with today's date.
    Since all sample data is effective 2026-07-02, any class created after that
    would read as inactive on the seed date and vanish from the allocation
    screens. Only ever moves dates earlier, so it is safe to re-run.

    Args:
        session: Active SQLAlchemy session (caller is responsible for commit).
    """
    for asset_class in session.scalars(select(AccountAssetClass)).all():
        if asset_class.date_created > _SEED_DATE:
            asset_class.date_created = _SEED_DATE


def seed_balance_sheet(session: Session) -> dict[str, Account]:
    """Seed the household's accounts and holdings if the accounts table is empty.

    Args:
        session: Active SQLAlchemy session (caller is responsible for commit).

    Returns:
        The seeded accounts keyed by name, or the already-present accounts when
        the seed was skipped, so downstream steps can wire up goals and
        contributions either way.
    """
    if session.scalar(select(Account)) is not None:
        print("Balance sheet accounts already present — skipping seed.")
        return {a.name: a for a in session.scalars(select(Account)).all()}

    persons = {p.name: p for p in session.scalars(select(Person)).all()}
    if not persons:
        raise RuntimeError("No persons found. Run initialize_database first.")
    mom_only = [persons["Mom"]]
    dad_only = [persons["Dad"]]
    both = mom_only + dad_only

    ac = {row.name: row for row in session.scalars(select(AccountAssetClass)).all()}

    # ── Current assets ────────────────────────────────────────────────────────
    _simple(session, both, "Joint Chequing", _ASSET_CUR, SimpleAccountCategory.BANK,
            Decimal("10000.00"))
    _simple(session, both, "Joint Savings", _ASSET_CUR, SimpleAccountCategory.BANK,
            Decimal("40000.00"))

    emergency_gic = _investment(session, both, "Emergency Fund GIC", _ASSET_CUR,
                                InvestmentRegistration.UNREGISTERED)
    _exact(session, emergency_gic, ac, "3.00% 1-Year Cashable GIC", Decimal("30000.00"),
           {"Fixed Income": Decimal("100")})

    # ── Long-term assets: property and vehicles ───────────────────────────────
    _simple(session, both, "Home", _ASSET_LT, SimpleAccountCategory.REAL_ESTATE,
            Decimal("800000.00"))
    _simple(session, mom_only, "Mom's CR-V", _ASSET_LT,
            SimpleAccountCategory.VEHICLE, Decimal("40000.00"))
    _simple(session, dad_only, "Dad's Camry", _ASSET_LT, SimpleAccountCategory.VEHICLE,
            Decimal("35000.00"))

    # ── Long-term assets: Mom's direct investing accounts ─────────────────────
    # Share counts across the five retirement accounts are chosen so the pooled
    # holdings land within about a point of the Retirement goal's target mix,
    # apart from a deliberate APAC underweight.
    moms_rrsp = _investment(session, mom_only, "Mom's RRSP", _ASSET_LT,
                            InvestmentRegistration.RRSP, Decimal("3000.00"))
    _listed(session, moms_rrsp, ac, "ZAG.TO", 4000)
    _listed(session, moms_rrsp, ac, "XBB.TO", 1500)
    _listed(session, moms_rrsp, ac, "XIC.TO", 500)
    _listed(session, moms_rrsp, ac, "ZSP.TO", 700)
    _listed(session, moms_rrsp, ac, "XEF.TO", 700)
    _listed(session, moms_rrsp, ac, "ZEM.TO", 700)

    moms_tfsa = _investment(session, mom_only, "Mom's TFSA", _ASSET_LT,
                            InvestmentRegistration.TFSA, Decimal("1500.00"))
    _listed(session, moms_tfsa, ac, "ZCN.TO", 500)
    _listed(session, moms_tfsa, ac, "XUU.TO", 700)
    _listed(session, moms_tfsa, ac, "ZEA.TO", 600)
    _listed(session, moms_tfsa, ac, "ZRE.TO", 400)

    # ── Long-term assets: Dad's direct investing accounts ─────────────────────
    dads_rrsp = _investment(session, dad_only, "Dad's RRSP", _ASSET_LT,
                            InvestmentRegistration.RRSP, Decimal("2000.00"))
    _listed(session, dads_rrsp, ac, "ZAG.TO", 2200)
    _listed(session, dads_rrsp, ac, "ZCN.TO", 700)
    _listed(session, dads_rrsp, ac, "ZSP.TO", 300)
    _listed(session, dads_rrsp, ac, "XEF.TO", 800)
    _listed(session, dads_rrsp, ac, "XEC.TO", 700)

    dads_tfsa = _investment(session, dad_only, "Dad's TFSA", _ASSET_LT,
                            InvestmentRegistration.TFSA, Decimal("1000.00"))
    _listed(session, dads_tfsa, ac, "XIC.TO", 250)
    _listed(session, dads_tfsa, ac, "XUU.TO", 400)
    _listed(session, dads_tfsa, ac, "ZEA.TO", 1000)
    _listed(session, dads_tfsa, ac, "ZRE.TO", 600)

    # ── Long-term assets: Dad's employer plan ─────────────────────────────────
    # Group plan units are not listed, so they are tracked as exact amounts.
    dads_group_rrsp = _investment(session, dad_only, "Dad's Group RRSP", _ASSET_LT,
                                  InvestmentRegistration.RRSP, Decimal("2000.00"))
    _exact(session, dads_group_rrsp, ac, "Sun Life Granite 2045 Fund", Decimal("40000.00"), {
        "Cash": Decimal("2"),
        "Fixed Income": Decimal("20"),
        "Canadian Equity": Decimal("18"),
        "US Equity": Decimal("30"),
        "European Equity": Decimal("15"),
        "APAC Equity": Decimal("8"),
        "Emerging Equity": Decimal("7"),
    })
    _exact(session, dads_group_rrsp, ac, "Sun Life Canadian Bond Fund", Decimal("18000.00"),
           {"Fixed Income": Decimal("100")})

    # ── Long-term assets: the child's education savings ───────────────────────
    # Dad has contributed $500/month for five years ($30,000) plus growth, held
    # in a single balanced ETF topped up with bonds as the horizon shortens.
    resp = _investment(session, dad_only, "Child's RESP", _ASSET_LT,
                       InvestmentRegistration.RESP, Decimal("500.00"))
    _listed(session, resp, ac, "ZBAL.TO", 2000)
    _listed(session, resp, ac, "XBB.TO", 150)

    # ── Current liabilities ───────────────────────────────────────────────────
    _simple(session, mom_only, "Mom's Visa", _LIAB_CUR,
            SimpleAccountCategory.RECEIVABLE_PAYABLE, Decimal("2000.00"))
    _simple(session, dad_only, "Dad's MasterCard", _LIAB_CUR,
            SimpleAccountCategory.RECEIVABLE_PAYABLE, Decimal("1500.00"))

    # ── Long-term liabilities ─────────────────────────────────────────────────
    _simple(session, both, "Mortgage", _LIAB_LT, SimpleAccountCategory.REAL_ESTATE,
            Decimal("200000.00"))

    session.flush()
    accounts = {a.name: a for a in session.scalars(select(Account)).all()}
    print(f"Seeded {len(accounts)} accounts for {_SEED_DATE}.")
    return accounts


def seed_goals(session: Session, accounts: dict[str, Account]) -> dict[str, Goal]:
    """Seed the household's goals if the goals table is empty.

    Bank claims total $55,000 against $50,000 of bank balances, which is what
    surfaces the overclaim warning on the Goals screen.

    Args:
        session: Active SQLAlchemy session (caller is responsible for commit).
        accounts: Balance sheet accounts keyed by name.

    Returns:
        The seeded goals keyed by name, or the already-present goals when the
        seed was skipped.
    """
    if session.scalar(select(Goal)) is not None:
        print("Goals already present — skipping seed.")
        return {g.name: g for g in session.scalars(select(Goal)).all()}

    ac = {row.name: row for row in session.scalars(select(AccountAssetClass)).all()}

    def investment(name: str) -> InvestmentAccount:
        account = accounts[name]
        assert isinstance(account, InvestmentAccount)
        return account

    # ── Rainy day — $45k target, GIC allocated, bank AutoFills the $15k gap ───
    _goal(
        session, "Rainy day",
        _scalar_value(Decimal("45000.00")),
        GoalBankPortionAutoFill(),
        ac, {"Cash": Decimal("20"), "Fixed Income": Decimal("80")},
        [investment("Emergency Fund GIC")],
    )

    # ── Vacation — $20k target held entirely in cash ──────────────────────────
    _goal(
        session, "Vacation",
        _scalar_value(Decimal("20000.00")),
        GoalBankPortionAutoFill(),
        ac, {"Cash": Decimal("100")},
    )

    # ── New vehicle — PV of $50,000 five years out at 4% ──────────────────────
    _goal(
        session, "New vehicle",
        SimplePVGoalValue(
            future_value=Decimal("50000.00"),
            start_date=_SEED_DATE,
            maturity_date=date(2031, 7, 2),
            discount_rate=Decimal("0.04"),
        ),
        _scalar_bank(Decimal("10000.00")),
        ac, {"Cash": Decimal("50"), "Fixed Income": Decimal("50")},
    )

    # ── Education — balanced mix, the money is needed in 10–15 years ──────────
    # PV of $100,000 needed by 2040, saved from 2021 at 5% — roughly $39,600
    # today, which the RESP plus the bank claim already exceed. This is the one
    # goal that sits in surplus.
    _goal(
        session, "Education",
        SimplePVGoalValue(
            future_value=Decimal("100000.00"),
            start_date=date(2021, 1, 1),
            maturity_date=date(2040, 1, 1),
            discount_rate=Decimal("0.05"),
        ),
        _scalar_bank(Decimal("10000.00")),
        ac, {
            "Cash": Decimal("2"),
            "Fixed Income": Decimal("38"),
            "Canadian Equity": Decimal("15"),
            "US Equity": Decimal("25"),
            "European Equity": Decimal("10"),
            "APAC Equity": Decimal("5"),
            "Emerging Equity": Decimal("5"),
        },
        [investment("Child's RESP")],
    )

    # ── Retirement — no cap, growth-tilted, everything long-term allocated ────
    # An explicit $0 bank claim rather than AutoFill: the retirement pool is
    # entirely invested, and a scalar keeps the bank cell an editable $0 instead
    # of a derived one.
    _goal(
        session, "Retirement",
        NoGoalValue(),
        _scalar_bank(Decimal("0.00")),
        ac, {
            "Cash": Decimal("1.5"),
            "Fixed Income": Decimal("22"),
            "Canadian Equity": Decimal("15"),
            "US Equity": Decimal("30"),
            "European Equity": Decimal("12"),
            "APAC Equity": Decimal("8"),
            "Emerging Equity": Decimal("8"),
            "Other": Decimal("3.5"),
        },
        [
            investment("Mom's RRSP"),
            investment("Mom's TFSA"),
            investment("Dad's RRSP"),
            investment("Dad's TFSA"),
            investment("Dad's Group RRSP"),
        ],
    )

    session.flush()
    goals = {g.name: g for g in session.scalars(select(Goal)).all()}
    print(f"Seeded {len(goals)} goals for {_SEED_DATE}.")
    return goals


def seed_cash_flow(
    session: Session,
    accounts: dict[str, Account],
    goals: dict[str, Goal],
) -> None:
    """Seed income profiles, household expenses and automated contributions.

    Income profiles are updated in place — ``initialize_database`` already
    created an empty one per person — and are only populated when still blank,
    so re-running does not stack duplicate timeline entries.

    Args:
        session: Active SQLAlchemy session (caller is responsible for commit).
        accounts: Balance sheet accounts keyed by name.
        goals: Goals keyed by name.
    """
    profiles = {
        p.person.name: p
        for p in session.scalars(select(PersonalCashFlowProfile)).all()
    }

    if all(p.gross_annual_income.latest_value_as_of(_SEED_DATE) is None
           for p in profiles.values()):
        # Mom out-earns Dad and has no employer plan; Dad's 5% payroll RRSP is
        # matched 5% by his employer, both landing in his group RRSP.
        mom_profile = profiles["Mom"]
        mom_profile.date_modified = _SEED_DATE
        mom_profile.gross_annual_income.offer_value(_SEED_DATE, Decimal("140000.00"))
        mom_profile.net_annual_income.offer_value(_SEED_DATE, Decimal("98000.00"))
        mom_profile.gross_bonus.offer_value(_SEED_DATE, Decimal("15000.00"))
        mom_profile.net_bonus.offer_value(_SEED_DATE, Decimal("8000.00"))
        mom_profile.auto_rrsp_deducted.offer_value(_SEED_DATE, Decimal("0.00"))
        mom_profile.rrsp_matched.offer_value(_SEED_DATE, Decimal("0.00"))

        dad_profile = profiles["Dad"]
        dad_profile.date_modified = _SEED_DATE
        dad_profile.gross_annual_income.offer_value(_SEED_DATE, Decimal("110000.00"))
        dad_profile.net_annual_income.offer_value(_SEED_DATE, Decimal("76000.00"))
        dad_profile.gross_bonus.offer_value(_SEED_DATE, Decimal("0.00"))
        dad_profile.net_bonus.offer_value(_SEED_DATE, Decimal("0.00"))
        dad_profile.auto_rrsp_deducted.offer_value(_SEED_DATE, Decimal("5500.00"))
        dad_profile.rrsp_matched.offer_value(_SEED_DATE, Decimal("5500.00"))
        dad_profile.auto_rrsp_goal = goals["Retirement"]
        print(f"Seeded {len(profiles)} cash flow profiles for {_SEED_DATE}.")
    else:
        print("Cash flow profiles already populated — skipping seed.")

    # ── Household expenses — $6,000/month ─────────────────────────────────────
    if session.scalar(select(HouseholdExpense)) is None:
        expenses: list[tuple[str, str, HouseholdExpenseClassification,
                             HouseholdExpenseSource, HouseholdExpenseFrequency]] = [
            ("Mortgage payment", "1500.00", _HOME, _BANK_PAID, _REGULAR),
            ("Property tax", "500.00", _HOME, _BANK_PAID, _REGULAR),
            ("Home insurance", "150.00", _HOME, _BANK_PAID, _REGULAR),
            ("Hydro, gas and water", "350.00", _HOME, _BANK_PAID, _REGULAR),
            ("Internet and mobile", "200.00", _HOME, _CREDIT_PAID, _REGULAR),
            ("Home maintenance", "200.00", _HOME, _BANK_PAID, _IRREGULAR),
            ("Auto insurance", "250.00", _AUTO, _BANK_PAID, _REGULAR),
            ("Fuel", "250.00", _AUTO, _CREDIT_PAID, _REGULAR),
            ("Vehicle maintenance", "100.00", _AUTO, _CREDIT_PAID, _IRREGULAR),
            ("Groceries", "1100.00", _OTHER, _CREDIT_PAID, _REGULAR),
            ("Dining out", "300.00", _OTHER, _CREDIT_PAID, _REGULAR),
            ("Childcare and activities", "400.00", _OTHER, _BANK_PAID, _REGULAR),
            ("Subscriptions and entertainment", "150.00", _OTHER, _CREDIT_PAID, _REGULAR),
            ("Clothing", "150.00", _OTHER, _CREDIT_PAID, _IRREGULAR),
            ("Gifts and holidays", "150.00", _OTHER, _CREDIT_PAID, _IRREGULAR),
            ("Health and dental", "100.00", _OTHER, _OTHER_PAID, _REGULAR),
            ("Charitable giving", "150.00", _OTHER, _OTHER_PAID, _IRREGULAR),
        ]
        for name, amount, classification, source, frequency in expenses:
            _expense(session, name, Decimal(amount), classification, source, frequency)
        print(f"Seeded {len(expenses)} household expenses for {_SEED_DATE}.")
    else:
        print("Household expenses already present — skipping seed.")

    # ── Automated contributions — $4,500/month out of chequing ────────────────
    if session.scalar(select(AutomatedContribution)) is None:
        chequing = accounts["Joint Chequing"]
        contributions = [
            ("RESP contribution", "500.00", "Child's RESP", "Education"),
            ("Mom's RRSP contribution", "1500.00", "Mom's RRSP", "Retirement"),
            ("Mom's TFSA contribution", "1000.00", "Mom's TFSA", "Retirement"),
            ("Dad's TFSA contribution", "1000.00", "Dad's TFSA", "Retirement"),
            ("Vacation savings", "500.00", "Joint Savings", "Vacation"),
        ]
        for name, amount, destination, goal_name in contributions:
            _contribution(session, name, Decimal(amount), chequing,
                          accounts[destination], goals[goal_name])
        print(f"Seeded {len(contributions)} automated contributions for {_SEED_DATE}.")
    else:
        print("Automated contributions already present — skipping seed.")


def main() -> None:
    """Run the full seed: config data, balance sheet, goals and cash flow."""
    config = load_config()
    engine = create_db_engine()
    initialize_database(engine, config)

    with Session(engine) as session:
        backdate_asset_classes(session)
        accounts = seed_balance_sheet(session)
        goals = seed_goals(session, accounts)
        seed_cash_flow(session, accounts, goals)
        session.commit()

    print(f"Database ready at {get_db_path()}")


if __name__ == "__main__":
    main()
