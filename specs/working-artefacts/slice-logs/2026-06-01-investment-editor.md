# Slice: Investment Editor

**Date:** 2026-06-01
**Status:** Complete

## Description

Delivers the investment account editor flows: `F-6` (`InvestmentEditorScreen`), `F-7a`
(`AddHoldingDialog`), and `F-7b` (`HoldingAllocationDialog`). Also completes the
deferred `BS-OP-3` full path (classification/registration edit) and implements `BS-OP-13`
(symbol search/typeahead).

This slice picks up directly from the handoff in
[2026-05-27-balance-sheet.md](2026-05-27-balance-sheet.md): the stub
`BalanceSheetScreen.action_open_investment` in `ui/screens/balance_sheet.py` is replaced with a
real `push_screen` to `InvestmentEditorScreen`.

## Specification References

### UI Flows to Implement

- [x] `F-6` (View & Edit Investment Holdings)
  - `InvestmentEditorScreen` launched from `BalanceSheetScreen.action_open_investment`
  - Editable cash balance (BS-OP-7)
  - Holdings table: listed (Name/Symbol static, Qty editable) and exact (Name/Total editable)
  - Gold-bordered read-only allocation cell per row; F6 when focused → F-7b
  - Read-only Total bar fixed below scroll area (cash + holding totals); updates in-place on edit
  - `F2` → F-7a, `F8` → discard focused holding, `Esc` → F-4
  - References: `BS-OP-6`, `BS-OP-7`, `BS-OP-9`, `BS-OP-10`, `BS-OP-11`

- [x] `F-7a` (Add Holding Dialog)
  - Type radio: Listed Security / Manual Entry
  - Listed path: Symbol typeahead (BS-OP-13), Quantity input; Name/Unit Price/Total static
  - Manual path: Name and Total inputs
  - Inline Asset Allocation section (all active `AccountAssetClass`es, must sum to 100%)
  - `[Cancel]` / `[Create]` buttons
  - References: `BS-OP-8`, `BS-OP-13`

- [x] `F-7b` (Edit Asset Allocation Dialog)
  - All active `AccountAssetClass`es with percentage inputs
  - Total display; must sum to 100%
  - `[Cancel]` / `[ Save ]` buttons
  - References: `BS-OP-12`

### Operations to Implement

- [x] `BS-OP-6` (Get Investment Account Details) — `BalanceSheetService.get_investment_account_details` + `BalanceSheetAppService.get_investment_details`
- [x] `BS-OP-7` (Update Uninvested Cash Balance) — `BalanceSheetService.update_uninvested_cash_balance` + `BalanceSheetAppService`
- [x] `BS-OP-8` (Add Holding) — `BalanceSheetService.add_holding` + `BalanceSheetAppService`
- [x] `BS-OP-9` (Update Holding Exact Amount) — `BalanceSheetService.update_holding_exact_amount` + `BalanceSheetAppService`
- [x] `BS-OP-10` (Update Holding Listed Security Quantity) — `BalanceSheetService.update_holding_listed_quantity` + `BalanceSheetAppService`
- [x] `BS-OP-11` (Discard Holding) — `BalanceSheetService.discard_holding` + `BalanceSheetAppService`
- [x] `BS-OP-12` (Update Holding Asset Allocation) — `BalanceSheetService.update_holding_asset_allocation` + `BalanceSheetAppService`
- [x] `BS-OP-13` (Search Securities) — add `search_symbols` to `QuoteService` ABC and `YahooFinanceQuoteService`
- [x] Asset class listing — `BalanceSheetService.list_active_asset_classes` + `BalanceSheetAppService.get_asset_classes` (supporting F-7a and F-7b allocation forms)

## Dependencies

- [2026-05-27-balance-sheet.md](2026-05-27-balance-sheet.md) — balance sheet summary screen,
  `BalanceSheetService`, `BalanceSheetAppService`, `Discardable` mixin with `date_effective`/
  `date_modified`, `HoldingAssetClassAllocation` domain entity.

## ADRs

### Referenced

- None yet identified.

### Created

- None yet.

## Decisions Made

- **BS-OP-3 full deferred indefinitely.** Editing an account's classification or registration is
  too rare to warrant a dialog. Name-only editing (the existing partial BS-OP-3) is sufficient.
  Removed from this slice's operation list.

- **Typeahead UX (F-7a symbol field):** Enter triggers a `BS-OP-13` search and shows the top 5
  results as radio buttons in a list below the input. No result is auto-selected; focus moves to
  the first radio button after the search completes. Re-entering a new search string clears the
  prior selection. This is approach (a) + (c) hybrid.

- **`search_symbols` added to `QuoteService` ABC first.** Extending `core/interfaces.py` and
  `YahooFinanceQuoteService` is the first task of this slice before any other F-7a work.

- **Unit price injection instead of total (domain model change).** `ListedSecurityHolding`
  now stores the unit price as its transient field (via `setUnitPrice(as_of, price_per_share)`)
  instead of the pre-multiplied total. `get_value(effective_date)` computes
  `unit_price × quantity.latestValueAsOf(effective_date)` on the fly. After a BS-OP-10 quantity
  edit, the F-6 total column can update without a new network call — provided the in-memory
  instance still holds the unit price from the initial screen load. Data requirements spec
  updated accordingly.

- **`Ins` key changed to `F2` for adding a holding.** The `F-7a` flow is triggered by `F2`
  (not `Ins` as originally specified in the UI flow) for consistency with the Balance Sheet
  Summary screen, which also uses `F2` / `F3` for creation. The spec wireframe footer updated
  accordingly: `[F2] Add Holding`.

- **Allocation `[Create]`/`[Save]` button disabled until sum == 100%.** No inline error message
  needed; the disabled state is sufficient feedback.

- **BS-OP-12 overwrite semantics confirmed.** Discard existing active
  `HoldingAssetClassAllocation` records via `discard(as_of)`, then insert new records with
  `date_effective = as_of`. Multiple overwrites on the same calendar day will produce allocation
  sets with the same `date_discarded`; serial primary key ordering is sufficient to determine
  precedence for any reporting purpose.

## Uncertainties

- [x] **U-1 — Typeahead widget:** Resolved — Enter-to-search with radio button list (see Decisions Made).
- [x] **U-2 — `search_symbols` in ABC:** Resolved — extend ABC and implementation first.
- [x] **U-3 — BS-OP-3 full scope:** Resolved — deferred indefinitely.
- [x] **U-4 — Re-pricing after quantity edit:** Resolved — unit price injection approach (see Decisions Made). One follow-on note: after `session.commit()` in BS-OP-10, SQLAlchemy expires in-memory instances, so the transient unit price is lost on the next attribute access. The F-6 screen must re-call `get_investment_details` (which re-prices via the quote service) after commits that expire the session, or hold unit prices in the app-service response for re-use. This will be resolved at implementation time.
- [x] **U-5 — Allocation sum UX:** Resolved — button disabled until sum == 100%.
- [x] **U-6 — BS-OP-12 overwrite semantics:** Resolved — discard + re-insert pattern confirmed.

## Handoff Notes

- **U-4 resolution (unit price after quantity commit):** `InvestmentEditorScreen` reads the
  `unit_price` from the `AllocationDisplay` widget on the focused row *before* committing the
  quantity change. If the price is available, the new total is computed in-memory and displayed
  immediately without a network round-trip. If not (e.g., the widget was never priced), the screen
  falls back to a full `get_investment_details` reload via `_load_data()`. This avoids the
  post-`commit()` SQLAlchemy expiry issue described in U-4.

- **`update_holding_name` is not in the slice log's operations list** but was added as a
  supporting helper (`BalanceSheetService.update_holding_name` /
  `BalanceSheetAppService.update_holding_name`) to allow renaming exact holdings inline in
  F-6. It is a straightforward single-field write with no domain invariants.

- **No follow-on slices identified.** All investment editor flows are complete. The next work area
  is likely reporting or a new module.

---

*This slice-log is a working-artefact specification. It is not actively maintained after the slice is complete.*
