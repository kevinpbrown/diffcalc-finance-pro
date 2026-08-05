# Slice: Balance Sheet

**Date:** 2026-05-27
**Status:** Complete

## Description

Delivers the **basic Balance Sheet** — the summary screen and simple-account management.
Implemented flows: F-4 (`BalanceSheetSummary`, including in-place name/balance editing and the
F8 discard path) and F-5 (`AccountCreationDialog`).

**Scope change (2026-05-31):** This slice was originally scoped to cover the *full* balance
sheet through F-7b. With the basic balance sheet complete for simple accounts, the investment
account screen and its dialogs — F-6 (`InvestmentEditorScreen`), F-7a (`AddHoldingDialog`),
and F-7b (`HoldingAllocationDialog`) — are **deferred to the next slice**, along with the
operations that back them (`BS-OP-3` full edit path and `BS-OP-8`–`BS-OP-12`). F-6's entry
point (`>`/F6 on an investment row) remains a stub notification in this slice. See Handoff Notes.

## Specification References

### UI Flows to Implement

- [x] `F-4` (View Balance Sheet Summary)
  - Accounts displayed in four sections with totals and net worth
  - In-place name editing (BS-OP-3 partial)
  - In-place balance editing for simple accounts (BS-OP-5)
  - Esc → Dashboard
  - F2, F3, F8 → stub notifications (dialogs are follow-on flows within this slice)
  - `>` drill on investment accounts → stub notification

- [x] `F-5` (Create Account Dialog)
  - Modal launched from F-4 via F2 (Asset) or F3 (Liability)
  - Account Name, Term Classification (radio), Nature (radio, assets only), Classification / Registration selects
  - Owner checkboxes (all active Persons; at least one required)
  - Up/Down navigation paused while a Select dropdown is expanded
  - Cancel / Create actions

- [x] `F-4` partial: F8 Discard Account
  - `ConfirmationDialog` (F-25) launched from F-4 via F8 on a focused account row
  - On confirmation, `BS-OP-4` is called and the balance sheet reloads
  - F8 footer hint is hidden when focus is not on an account-row widget

**Deferred to next slice (investment accounts):**

- [ ] `F-6` (View & Edit Investment Holdings) — *deferred*
  - Launched from F-4 via `>` on an investment account row
  - Editable cash balance; holdings table (listed and exact types)
  - Ins → F-7a, `>` on allocation column → F-7b, F8 → discard holding, Esc → F-4
  - Currently a stub notification on F6 from the focused investment balance display.

- [ ] `F-7a` (Add Holding Dialog) — *deferred*
  - Modal launched from F-6 via `Ins`
  - Type radio (Listed Security / Manual Entry), security-specific fields, asset allocation section

- [ ] `F-7b` (Edit Asset Allocation Dialog) — *deferred*
  - Modal launched from F-6 via holding `>` button
  - List of active `AccountAssetClass`es with percentage inputs, must sum to 100 %

### Operations to Implement

- [x] `BS-OP-1` (Get Balance Sheet Summary) — `BalanceSheetAppService.get_summary`
- [x] `BS-OP-3` partial (Update Account Name only) — `BalanceSheetAppService.update_account_name`
- [x] `BS-OP-5` (Update Simple Account Balance) — `BalanceSheetAppService.update_simple_account_balance`
- [x] `BS-OP-2` (Create Account) — `BalanceSheetAppService.create_account` / `BalanceSheetService.create_account`
- [x] `BS-OP-4` (Discard Account) — `BalanceSheetAppService.discard_account` / `BalanceSheetService.discard_account`
- [ ] `BS-OP-3` full (Update Account Classification/Registration) — *deferred* (F-5 edit path)
- [ ] Investment holding operations (BS-OP-8 through BS-OP-12) — *deferred* (F-6/F-7a/F-7b)

## Dependencies

- [2025-xx-xx-tui-bootstrap](../slice-logs/) — Dashboard, session lifecycle, Splash, and
  service wiring patterns this slice follows.

## ADRs

### Referenced

- None yet identified.

### Created

- None yet.

## Decisions Made

- `BalanceSheetAppService` uses the `list_all_accounts` path (which prices listed security
  holdings) for every summary fetch, including after edits. This is correct but
  potentially slow once listed securities are present; noted as handoff item.
- After a name or balance commit the screen does a targeted update of total/net-worth
  Statics rather than a full rebuild, preserving focus position.
- Seed data uses only `SimpleAccount` and `InvestmentAccount` with `ExactHolding`
  entries (no `ListedSecurityHolding`) so the seed runs without a live quote service.
- `date_created` on new accounts is always `date.today()` (wall-clock audit timestamp). `date_effective` is set from the session's effective date at the time of creation (passed as `as_of` through the service layer). `date_modified` is initialized to `date.today()` on insert.
- `discard_account` takes an `as_of: date` parameter (the session effective date). The `Discardable.discard(as_of)` method enforces: `as_of` must be after `date_effective`; if already discarded, `as_of` must be strictly before `date_discarded` (allows correcting the discard date to an earlier value).
- **Domain Model Refinement (2026-05-29/30):** All `Discardable` entities gained `date_effective` and `date_modified` columns. `is_active(as_of)` now tests `date_effective <= as_of` (was `date_created`). Two new domain invariants: one active `HoldingAssetClassAllocation` per `AccountAssetClass` per holding; one active `GoalAssetClassTarget` per `AccountAssetClass` per goal. `AccountAssetClass` intentionally retains `date_disabled` (not `date_discarded`) — admin-managed config, not user-owned timeline entity.
- `Account.owner_id` (single FK) replaced with a Many-to-Many `owners` relationship via an
  `account_owners` junction table, enabling multi-owner households. `create_account` now requires
  at least one `owner_id` in the `owner_ids` list; zero owners raises `ValueError`.
- `AccountCreationDialog` uses `Checkbox` widgets (one per active Person) for owner selection.
  Attempting to create with zero owners checked shows an inline error notification.
- `AccountCreationDialog` uses `RadioSet`/`RadioButton` for both Term Classification and Nature
  fields (replacing the original dropdown design).
- `AccountCreationDialog` lives in `ui/screens/balance_sheet_dialogs.py` (separate from the
  shared `dialogs.py`) since it is balance-sheet-specific.

## Uncertainties

- [x] The technical charter mandates `updated_at` on domain entities for update
      operations. Resolved by adding `date_modified` to all `Discardable` entities and
      `PersonalCashFlowProfile` (see Domain Model Refinement section under Decisions Made).
- [x] Up/Down key navigation interacts with `Select` internal key handling — resolved by
      checking `select.expanded` before intercepting arrow keys in `AccountCreationDialog`.
- [x] F-5 had no owner selector. Resolved by migrating to Many-to-Many ownership and adding
      per-person `Checkbox` widgets to `AccountCreationDialog`.

## Handoff Notes

### Next slice: Investment accounts (F-6, F-7a, F-7b)

- The next slice picks up the deferred investment account work: `F-6` (`InvestmentEditorScreen`),
  `F-7a` (`AddHoldingDialog`), and `F-7b` (`HoldingAllocationDialog`).
- `F-6`'s entry point is already present: pressing `F6` while a gold-bordered
  `InvestmentBalanceDisplay` is focused calls `action_open_investment`, which currently fires a
  stub `notify` ("Investment Editor not yet implemented"). Replace the stub with a `push_screen`
  to the new editor (see `BalanceSheetScreen.action_open_investment` in
  `ui/screens/balance_sheet.py`).
- Backing operations to implement: `BS-OP-3` full (classification/registration edit, also needed
  for an F-5 edit path) and the holding operations `BS-OP-8`–`BS-OP-12`.
- Seed data currently has no `ListedSecurityHolding` rows (the seed must run without a live
  quote service). The investment slice will need a strategy for exercising the priced path — e.g.
  a fake/injected quote provider in tests.

### General

- `F-25` (`ConfirmationDialog` for discard) is wired and used by the F8 discard path. It is a
  shared dialog outside the Balance Sheet spec; any further generalisation is out of scope here.
- All current scalar-field mutation operations (`update_account_name`) now set
  `date_modified = date.today()`. Future operations that mutate scalar fields on entities must do
  the same.
- Post-edit `_refresh_totals` re-runs `list_all_accounts` (including quote-service calls for any
  listed securities). Add caching or a cheaper query path before listed securities are commonly
  used.

### Closure quality gates (2026-05-31)

- `pytest -m "not external"`: **234 passed**, total coverage **90%** (≥ 80% gate; core service
  modules at 100%).
- `ruff check src tests`: clean. `mypy --strict src`: clean.
- `ruff format`: all 17 slice-touched files formatted as part of closing this slice. Two files —
  `src/personal_finance/db.py` and `tests/integrations/test_yahoo_finance.py` — remain unformatted
  but were **not touched by this slice**; they are flagged for whichever slice next modifies them
  (the format-on-save / pre-commit workflow mandated by the charter is not yet wired up).

---

*This slice-log is a working-artefact specification. It is not actively maintained after the slice is complete.*
