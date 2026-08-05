# Service Operations (Layer 2)

This document defines the named operations on domain entities, their preconditions, postconditions, and side-effects. These operations are implemented as "transaction scripts" in the service layer, fulfilling requests from the Textual UI.

## General Operations

### GEN-OP-1: Get Amount Left to Invest
- **Description:** Calculates the available cash cushion for new long-term investments.
- **Inputs:** `effectiveDate` (date)
- **Preconditions:** None.
- **Postconditions/Side-effects:** Returns `Σ(Bank values) - Σ(Current Liability values) - Σ(Goal claims on Bank accounts) - amount_left_to_invest_cushion` as of `effectiveDate`.

## Balance Sheet Operations

### BS-OP-1: Get Balance Sheet Summary
- **Description:** Retrieves the aggregated list of active accounts grouped by asset/liability and term classification.
- **Inputs:** `effectiveDate` (date)
- **Preconditions:** None.
- **Postconditions/Side-effects:** Returns aggregated account list, calculating each account's value based on `effectiveDate`. Computes Current Assets, Long-Term Assets, Current Liabilities, Long-Term Liabilities, Current Net Worth, and Total Net Worth.

### BS-OP-2: Create Account
- **Description:** Creates a new Simple or Investment account.
- **Inputs:** `name`, `termClassification` (Current/Long-Term), `nature` (Simple/Investment), `classification` (if Simple), `registration` (if Investment)
- **Preconditions:** Valid classification/registration for the selected nature.
- **Postconditions/Side-effects:** A new `Account` (or subclass) is persisted with `dateCreated` set to now.

### BS-OP-3: Update Account Metadata
- **Description:** Updates the editable metadata of an existing account.
- **Inputs:** `accountId`, `name`, `termClassification`, `classification`/`registration`, `ownerIds`
- **Preconditions:** Account exists and is active. At least one `ownerId` must be provided.
- **Postconditions/Side-effects:** Account properties are updated.
- **Constraints:** `nature` (Simple vs Investment) is not an input and cannot be changed after creation.

### BS-OP-4: Discard Account
- **Description:** Soft-deletes a financial account.
- **Inputs:** `accountId`
- **Preconditions:** Account exists and is active.
- **Postconditions/Side-effects:** Sets `dateDiscarded` on the account, removing it from active summaries.

### BS-OP-5: Update Simple Account Balance
- **Description:** Records an updated temporal balance for a Simple Account.
- **Inputs:** `accountId`, `effectiveDate`, `newBalance`
- **Preconditions:** Account exists and is a `SimpleAccount`.
- **Postconditions/Side-effects:** Appends a new `EffectiveAmountEntry` to the `balance` timeline mapping to `effectiveDate`.

### BS-OP-6: Get Investment Account Details
- **Description:** Retrieves the holdings and uninvested cash balance of an investment account.
- **Inputs:** `accountId`, `effectiveDate`
- **Preconditions:** Account exists and is an `InvestmentAccount`.
- **Postconditions/Side-effects:** Returns uninvested cash balance, list of exact/listed holdings, calculated holding totals, and asset allocation mappings.

### BS-OP-7: Update Uninvested Cash Balance
- **Description:** Records an updated temporal value for uninvested cash.
- **Inputs:** `accountId`, `effectiveDate`, `newBalance`
- **Preconditions:** Account exists and is an `InvestmentAccount`.
- **Postconditions/Side-effects:** Appends a new `EffectiveAmountEntry` to the `cashBalance` timeline mapping to `effectiveDate`.

### BS-OP-8: Add Holding
- **Description:** Adds a holding to an investment account.
- **Inputs:** `accountId`, `type` (Exact/Listed), `name` or `symbol`/`initialQuantity`, `assetAllocations` (list of percentages)
- **Preconditions:** Account is active. Asset allocations must sum to 100%. `symbol` must be valid if Listed. `initialQuantity` must be positive if Listed.
- **Postconditions/Side-effects:** Persists an `ExactHolding` or `ListedSecurityHolding`. For a `ListedSecurityHolding`, an initial `quantity` timeline entry is created with `effectiveDate == dateCreated` and value == `initialQuantity`. Creates `HoldingAssetClassAllocation` records.

### BS-OP-9: Update Holding Exact Amount
- **Description:** Records an updated manual valuation for an exact holding.
- **Inputs:** `holdingId`, `effectiveDate`, `newAmount`
- **Preconditions:** Holding exists and is an `ExactHolding`.
- **Postconditions/Side-effects:** Appends a new `EffectiveAmountEntry` to the `amount` timeline mapping to `effectiveDate`.

### BS-OP-10: Update Holding Listed Security Quantity
- **Description:** Updates the held quantity for a listed security.
- **Inputs:** `holdingId`, `effectiveDate`, `newQuantity`
- **Preconditions:** Holding exists and is a `ListedSecurityHolding`.
- **Postconditions/Side-effects:** Appends a new entry to the `quantity` `EffectiveAmount` timeline mapping to `effectiveDate`.

### BS-OP-11: Discard Holding
- **Description:** Soft-deletes an investment holding.
- **Inputs:** `holdingId`
- **Preconditions:** Holding exists.
- **Postconditions/Side-effects:** Sets `dateDiscarded` on the holding.

### BS-OP-12: Update Holding Asset Allocation
- **Description:** Updates the underlying asset classification for a holding.
- **Inputs:** `holdingId`, `allocations` (list of class ID and percentages)
- **Preconditions:** Percentages must sum exactly to 100%. Holding exists.
- **Postconditions/Side-effects:** Overwrites `HoldingAssetClassAllocation` records for the holding.

### BS-OP-13: Search Securities
- **Description:** Queries an external provider for ticker symbols.
- **Inputs:** `query`
- **Preconditions:** External network connectivity.
- **Postconditions/Side-effects:** Returns matching list of symbols/names via yfinance autocorrect API.

## Goals Operations

### G-OP-1: Get Goals Summary
- **Description:** Retrieves all goals, evaluating their value strategies and asset allocations.
- **Inputs:** `effectiveDate`
- **Preconditions:** None.
- **Postconditions/Side-effects:** Returns goals with dynamically computed progress, Investment Account mapping sums, Bank claim sums, and an overclaimed Bank accounts warning if applicable.

### G-OP-2: Create Goal
- **Description:** Persists a new financial goal.
- **Inputs:** `name`, `valuationStrategy` (Manual, PV, No Target), strategy params (if PV: futureValue, startDate, maturityDate, discountRate; if Manual: value).
- **Preconditions:** None.
- **Postconditions/Side-effects:** Creates a `Goal` and associated `GoalValue` strategy.

### G-OP-3: Update Goal Definition
- **Description:** Modifies a goal's name and its underlying valuation strategy.
- **Inputs:** `goalId`, `name`, `valuationStrategy`, strategy params
- **Preconditions:** Goal exists.
- **Postconditions/Side-effects:** Updates the `Goal` entity and overhauls/updates the `GoalValue` strategy record.

### G-OP-4: Discard Goal
- **Description:** Soft-deletes a goal.
- **Inputs:** `goalId`
- **Preconditions:** Goal exists.
- **Postconditions/Side-effects:** Sets `dateDiscarded`. Disconnects any `allocatedAccounts`.

### G-OP-5: Update Goal Investment Allocation
- **Description:** Reassigns which Investment Accounts are dedicated to this Goal.
- **Inputs:** `goalId`, `accountIds`
- **Preconditions:** Goal exists. Selected accounts must be `InvestmentAccount`s and not currently assigned to another active Goal.
- **Postconditions/Side-effects:** Overwrites the `allocatedAccounts` list on the Goal.

### G-OP-6: Update Goal Bank Allocation Strategy
- **Description:** Sets how the goal claims from general bank funds.
- **Inputs:** `goalId`, `fillDifferenceFromBank` (boolean), `amountClaimedFromBank`
- **Preconditions:** Goal exists.
- **Postconditions/Side-effects:** Modifies bank claim properties on the Goal.

### G-OP-7: Get Goal Asset Allocations
- **Description:** Calculates target vs actual asset class allocation for a Goal.
- **Inputs:** `goalId`, `effectiveDate`
- **Preconditions:** Goal exists.
- **Postconditions/Side-effects:** Returns one row per active `AccountAssetClass` (ordered by `orderPrecedence`), each containing:
  - `targetPercent`: the goal's persisted `GoalAssetClassTarget.targetPercent` for that class, or 0% if no active record exists.
  - `actualPercent`: computed as `classValue / totalValue` where `totalValue = Σ(allocated InvestmentAccount balances) + bankPortionValue` and `classValue` is the portion of `totalValue` attributable to that class (bank portion contributes its full value to `BuiltInAssetClassId.CASH`; investment accounts contribute according to their holdings' `HoldingAssetClassAllocation` weights). When `totalValue` is $0, all `actualPercent` values are 0%.
  - `differencePercent`: `actualPercent − targetPercent`.
  - `differenceAmount`: `differencePercent × totalValue`.
  - Also returns a per-goal `[!]` flag: `targetSumExceeds100 = Σ(targetPercent) > 100%`.

### G-OP-8: Update Goal Asset Class Target
- **Description:** Defines the target portfolio composition percentages for a Goal.
- **Inputs:** `goalId`, `targets` (list of `(accountAssetClassId, targetPercent)` pairs), `effectiveDate`
- **Preconditions:** Goal exists. `Σ(targetPercent) ≤ 100%` (enforced by service; the UI validates this before calling). Each `accountAssetClassId` must refer to an active `AccountAssetClass`.
- **Postconditions/Side-effects:** Soft-deletes all currently active `GoalAssetClassTarget` records for the goal, then inserts a new record for each pair in `targets` with `dateEffective = effectiveDate`. Asset classes absent from `targets` receive no new record (implying 0% going forward). `GoalAssetClassTarget` rows with `targetPercent = 0` are written if explicitly included in `targets` but need not be if omitted.

## Cash Flow Operations

### CF-OP-1: Get Person Profiles Summary
- **Description:** Retrieves all people and their cash flow profiles.
- **Inputs:** `effectiveDate`
- **Preconditions:** None.
- **Postconditions/Side-effects:** Returns list of `Person`s and associated `PersonalCashFlowProfile` monetary components at the given `effectiveDate`.

### CF-OP-2: Update Person Cash Flow Profile
- **Description:** Updates the income and automated RRSP deductions for a person.
- **Inputs:** `profileId`, `effectiveDate`, properties (`grossAnnualIncome`, `netAnnualIncome`, `grossBonus`, `netBonus`, `autoRrspDeducted`, `autoRrspGoal`, `rrspMatched`).
- **Preconditions:** Profile exists. `grossAnnualIncome` > `netAnnualIncome`, `grossBonus` > `netBonus`. `rrspMatched > 0` requires `autoRrspDeducted > 0`.
- **Postconditions/Side-effects:** Modifies non-temporal linkages and injects new `EffectiveAmountEntry` items for temporal properties mapping to `effectiveDate`.

### CF-OP-3: Get Household Expenses Summary
- **Description:** Retrieves active expenses grouped by classification, including a cross-tabulated summary.
- **Inputs:** `effectiveDate`
- **Preconditions:** None.
- **Postconditions/Side-effects:** Returns `HouseholdExpense` list and calculates monthly summary aggregation based on values at `effectiveDate`.

### CF-OP-4: Create Household Expense
- **Description:** Persists a new expense item.
- **Inputs:** `name`, `amount`, `classification` (HOME, AUTO, OTHER), `source`, `frequency`, `effectiveDate`.
- **Preconditions:** None.
- **Postconditions/Side-effects:** Creates a `HouseholdExpense` and an initial `EffectiveAmountEntry` on its amount timeline.

### CF-OP-5: Update Household Expense
- **Description:** Modifies properties and records a new temporal amount.
- **Inputs:** `expenseId`, properties (`name`, `classification`, `source`, `frequency`), `newAmount`, `effectiveDate`.
- **Preconditions:** Expense exists.
- **Postconditions/Side-effects:** Updates scalar properties. Appends a new `EffectiveAmountEntry` mapping to `effectiveDate`.

### CF-OP-6: Discard Household Expense
- **Description:** Soft-deletes a household expense.
- **Inputs:** `expenseId`
- **Preconditions:** Expense exists.
- **Postconditions/Side-effects:** Sets `dateDiscarded`.

### CF-OP-7: Get Household Cash Flow Report
- **Description:** Generates the aggregated monthly/annual projection report.
- **Inputs:** `effectiveDate`
- **Preconditions:** None.
- **Postconditions/Side-effects:** Calculates Total Gross/Net incomes, deducts average expenses, deducts automated contributions, and returns computed Total Monthly/Annual Retained metrics.

### CF-OP-8: Create Automated Contribution
- **Description:** Persists a new regular automated transfer.
- **Inputs:** `name`, `amount`, `sourceAccount`, `destinationAccount`, `targetGoal`, `effectiveDate`.
- **Preconditions:** Source account must exist.
- **Postconditions/Side-effects:** Creates `AutomatedContribution` with an initial `EffectiveAmountEntry`.

### CF-OP-9: Update Automated Contribution
- **Description:** Modifies properties and updates temporal amount.
- **Inputs:** `contributionId`, properties (`name`, `sourceAccount`, `destinationAccount`, `targetGoal`), `newAmount`, `effectiveDate`.
- **Preconditions:** Contribution exists.
- **Postconditions/Side-effects:** Updates scalar linkages. Appends a new `EffectiveAmountEntry` mapping to `effectiveDate`.

### CF-OP-10: Discard Automated Contribution
- **Description:** Soft-deletes an automated contribution.
- **Inputs:** `contributionId`
- **Preconditions:** Contribution exists.
- **Postconditions/Side-effects:** Sets `dateDiscarded`.
