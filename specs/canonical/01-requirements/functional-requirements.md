# Functional Requirements

This document defines the user capabilities and system behaviours in EARS format: "The [user/role] shall be able to..." with preconditions, postconditions, and notes.

## General Interaction

### GEN-1: Set Effective Date Context
**The user shall be able to specify a global "effective date" when entering the application or performing reporting and data entry operations.**

- **Precondition:** The date must not be in the future.
- **Postcondition:** The system uses the provided effective date for all subsequent queries and modifications related to the Balance Sheet and Cash Flow modules.
- **Notes:** Balance Sheet and Cash Flow models track monetary data on `EffectiveAmount` timelines. Read operations return the latest `EffectiveAmountEntry` on or before the effective date; write operations append a new entry at the effective date. While a goal's configuration (Target, Maturity Date) is scalar/timeless, evaluating its progress and active auto-fill allocations is intrinsically tied to the Session Effective Date.

## Balance Sheet Module

### BS‑1: View Balance Sheet
**The user shall be able to view the balance sheet as of the effective date, grouped by current vs long-term assets and liabilities, and both current and overall net worth.**

- **Precondition:** At least one account exists (asset or liability) active on the effective date.
- **Postcondition:** The system displays the aggregated values, grouped by term classification (Current vs Long-term).
- **Notes:** Totals calculated explicitly via the sum of account balances as of the effective date.

### BS‑2: Manage Accounts
**The user shall be able to create, read, update, and discard financial accounts (SimpleAccounts or InvestmentAccounts).**

- **Precondition:** None.
- **Postcondition:** The account is persisted with validated data, including an implicit or explicit DateCreated and Classification.
- **Notes:** Investment accounts require a registration type (e.g., RESP, TFSA, RRSP) rather than a simple classification. Simple accounts use categories like BANK, RECEIVABLE_PAYABLE, REAL_ESTATE. Updates to balances append new `EffectiveAmountEntry` items at the provided effective date. The Nature of an account (Simple vs Investment) is fixed at creation and cannot be changed afterwards.

### BS‑3: Manage Investment Holdings
**The user shall be able to add, edit, and remove holdings (holdings) within an investment account.**

- **Precondition:** An investment account exists and is active.
- **Postcondition:** The holding list is updated (either exact holding or listed security).
- **Notes:** For ExactHoldings (e.g., GICs), the user enters explicit monetary amount progressions over time. For ListedSecurityHoldings, they input quantities over time.

### BS‑4: Revalue Holdings
**The user shall be able to record an updated value for an account or holding as of the effective date.**

- **Precondition:** The account or holding exists.
- **Postcondition:** A new timeline entry (`EffectiveAmountEntry`) is appended to the entity's `EffectiveAmount` timeline.
- **Notes:** Supersedes existing entries if the exact effective date is matched. `ExactHolding`s update their `amount` progression, and `SimpleAccount`s update their `balance`. `ListedSecurityHolding`s do not require manual revaluation as their prices are fetched dynamically from the API (using the end-of-day value for previous days, or the most recent quote if the effective date is today).

### BS‑5: Search for Securities
**The user shall be able to search for a security ticker symbol via a typeahead input.**

- **Precondition:** Network connection to third-party data provider.
- **Postcondition:** User can select a validated security ticker ensuring it matches API expectations.
- **Notes:** Uses the `yfinance` public autocorrect endpoint over HTTPS.

## Goals Module

### G‑1: View Goal Progress
**The user shall be able to see a list of goals with their claimed amounts and progress toward target amounts.**

- **Precondition:** At least one goal exists.
- **Postcondition:** The system displays each goal’s name, total claimed amount, target amount (from its value strategy), and percentage achieved.
- **Notes:** While a goal's configuration is timeless (scalar), evaluating its progress and active allocations uses values as of the global effective date.

### G‑2: Manage Goals
**The user shall be able to create, read, update, and discard financial goals.**

- **Precondition:** None.
- **Postcondition:** Goals are configured with a `GoalValue` strategy (ScalarGoalValue, SimplePVGoalValue, or NoGoalValue) and a funding strategy.
- **Notes:** Goals are discarded using DateDiscarded.

### G‑3: Allocate Assets to Goals
**The user shall be able to commit entire investment accounts to a goal.**

- **Precondition:** At least one investment account and one goal exist.
- **Postcondition:** The investment account is appended to the goal's `allocatedAccounts`.
- **Notes:** An InvestmentAccount can be committed to at most one goal. This models dedicated accounts like an RESP or an entire RRSP.

### G‑4: Manage Bank Portion of Goal
**The user shall be able to configure how a goal claims cash from Bank classification accounts.**

- **Precondition:** A goal exists.
- **Postcondition:** The goal is updated to either use a explicit manual scalar claim (`GoalBankPortionScalar`), or to auto-fill the remaining amount needed (`GoalBankPortionAutoFill`).
- **Notes:** When using AutoFill, the goal claims exactly (Goal Target - Value of Allocated Investment Accounts) from available aggregate Bank balances. If the goal has a `NoGoalValue` strategy, AutoFill evaluates to a $0 claim.

### G‑5: Manage Goal Asset Class Targets
**The user shall be able to define the target portfolio composition for each goal by assigning percentages to active asset classes.**

- **Precondition:** At least one active AccountAssetClass and one Goal exists.
- **Postcondition:** `GoalAssetClassTarget` records are updated for the goal.
- **Notes:** The sum of target percentages may be under 100% (allowing unconstrained portions) but must not exceed 100%. The system provides visual validation and warnings if the total exceeds 100%. Actual allocations are calculated dynamically from the underlying accounts assigned to the goal. Bank claims and an investment account's uninvested cash balance are mapped automatically to 100% "Cash" for asset allocation tracking.

## Cash Flow & Expenses Module

### CF‑1: Manage Cash Flow Profiles
**The user shall be able to define and edit the annual income profile.**

- **Precondition:** None (Person is attached automatically).
- **Postcondition:** The `PersonalCashFlowProfile` is updated with values such as Gross/Net Annual Income, Bonuses, and matched RRSP values.
- **Notes:** Modifications to monetary values apply to the effective timeline using the global effective date.

### CF‑2: Manage Household Expenses
**The user shall be able to create, read, update, and discard household expenses.**

- **Precondition:** None.
- **Postcondition:** Expenses are persisted with name, classification (HOME, AUTO, OTHER), frequency, source, and a timeline-based monetary amount.
- **Notes:** Used strictly for planning and projections. Uses the timeline logic for average monthly amounts.

### CF‑3: View Cash Flow Projection
**The user shall be able to see a projected cash flow summary based on income profiles, expenses, and automated contributions.**

- **Precondition:** At least one Person profile or Household Expense exists active as of the effective date.
- **Postcondition:** The system displays projected monthly metrics (Income vs Expenses vs Contributions).
- **Notes:** All metrics pull values from the relevant `EffectiveAmount` timelines as of the global effective date.

### CF‑4: Manage Automated Contributions
**The user shall be able to define regular automated transfers.**

- **Precondition:** Source account exists.
- **Postcondition:** The AutomatedContribution record is saved with name, monetary amount, source/destination, assigned goal, and date bounds.
- **Notes:** Tracked over time. Destination account is optional (can represent untracked external spend).

## Reporting & Analytics

### R‑1: Calculate Amount Left to Invest
**The user shall be able to see the calculated excess bank cash available for new long-term investments as of the effective date.**

- **Precondition:** None.
- **Postcondition:** The system calculates: `Σ(Bank values) - Σ(Current Liability values) - Σ(Goal claims on Bank accounts) - amount_left_to_invest_cushion`.
- **Notes:** Pulls explicitly from the timeline as of the effective date.

### R‑2: View Net Worth History
**The user shall be able to view a chart or table of net worth over a time range.**

- **Precondition:** Balances have been entered at various dates.
- **Postcondition:** The system displays a time‑series chart mapping the aggregation of timeline changes across all active accounts.
- **Notes:** Unlike the prior architecture, this is rendered directly from the `EffectiveAmountEntry` timeline arrays across the portfolio, removing the need for manual static "Snapshots."

## Calculations & Validations

The system shall automatically perform the following calculations:

1. **Investment account value (as of date X)** = `cash_balance(X)` + Σ(holding explicit total value(X) OR (holding quantity × API_unit_price(X))).
2. **Simple account value (as of date X)** = `balance(X)`.
3. **Amount Left to Invest (as of date X)** = Σ(Current Asset Bank values at X) - Σ(Current Liability values at X) - Σ(Goal bank claims) - amount_left_to_invest_cushion.
4. **Calculated PV Goal Target** = Present value calculation using future value, start/maturity dates, and assumed discount rate.
5. **Goal Progress** = (Value of specific allocated investment accounts + Target Bank Portion Claim) / Goal Target.
6. **Required Monthly Payment** = PMT calculation using future value, months to maturity (from effective date), and discount rate.
7. **Current Net Worth (as of date X)** = Current Assets (X) - Current Liabilities (X).
8. **Total Net Worth (as of date X)** = Total Assets (X) - Total Liabilities (X).
9. **Total monthly gross income** = Σ(Person.grossAnnualIncome) / 12.
10. **Total monthly net income** = Σ(Person.netAnnualIncome) / 12.
11. **Average monthly expenses** = Σ(HouseholdExpense.amount).
12. **Total monthly retained** = Total monthly net income - Average monthly expenses - Σ(Automated contributions).
13. **Total annual retained** = (Total monthly retained × 12) + Σ(Person.netBonus).
14. **Total annual retained percentage** = Total annual retained / (Σ(Person.grossAnnualIncome) + Σ(Person.grossBonus)).
15. **Goal Cash Flow Contributions** = Σ(Person.autoRrspDeducted) + Σ(Person.rrspMatched) + Σ(AutomatedContribution.amount) grouped by assigned Goal.

All calculations must be consistent with the domain invariants defined in the Data Requirements document.
