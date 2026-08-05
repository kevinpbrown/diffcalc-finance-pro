# Slice: Goal Allocation View

**Date:** 2026-06-05
**Status:** Complete

## Description

Delivers Flow F-11b (`GoalAllocationView`): a two-pane screen where the user can
navigate the goal list (left) and define/review target vs. actual asset class
allocations for the selected goal (right). Implements G-OP-7 (Get Goal Asset
Allocations) and G-OP-8 (Update Goal Asset Class Target).

Replaces the "coming in a future slice" stub notification that currently fires
when F3 is pressed in `GoalsListScreen`.

## Specification References

### UI Flows to Implement

- [x] `F-11b` (Goal Allocation View — `GoalAllocationView`)
  - 33/67 split layout
  - Left pane: read-only navigable list of goals; `[!]` indicator when any
    goal's target percentages sum to > 100%
  - Right pane: all active `AccountAssetClass`es for the selected goal with
    editable Target%, read-only Actual%, and Difference columns
  - F7 bulk save → G-OP-8; dirty-flag guard on all navigation paths
  - `F3` → switch back to `GoalsListScreen` with selected goal pre-focused
  - `Esc` → Dashboard
  - References: G-OP-7, G-OP-8

### Operations to Implement

- [x] `G-OP-7` (Get Goal Asset Allocations) — `GoalService.get_goal_asset_class_targets`
  + `GoalAppService.get_goal_allocation_data` + `get_goals_for_allocation_view`
- [x] `G-OP-8` (Update Goal Asset Class Target) — `GoalService.update_goal_asset_class_targets`
  + `GoalAppService.update_goal_asset_class_targets`

## Dependencies

- [2026-06-03-goals.md](2026-06-03-goals.md) — GoalsList screen, all Goals
  domain models (`GoalAssetClassTarget`), G-OP-1 through G-OP-6 all complete.

## ADRs

### Referenced

- None yet identified.

### Created

- None yet.

## Decisions Made

- **U-1 resolved — Initial goal selection is bi-directional.** The goal focused
  in F-8 when F3 is pressed becomes the initially selected goal in F-11b. When
  F3 is pressed in F-11b to return, the goal selected in F-11b is pre-focused in
  F-8. Spec updated accordingly in both F-8 and F-11b.

- **U-2 resolved — Explicit F7 save; dirty-flag confirmation on navigate-away.**
  F-11b is an exception to the inline-persist pattern: all Target% edits are
  held in memory. F7 persists all values via G-OP-8 (full overwrite). A dirty
  flag tracks any in-memory change; any navigation (Esc, F3, left-pane goal
  switch) while dirty prompts `ConfirmationDialog("Discard unsaved changes?")`.
  F7 appears in the footer only when dirty and is blocked when sum > 100%.

- **U-3 resolved — `BuiltInAssetClassId.CASH = 1` (Option A, IntEnum + reserved PK).**
  `BuiltInAssetClassId` is an `IntEnum` defined alongside `AccountAssetClass`
  in `domain/asset_class.py`. The seed script inserts Cash with the reserved
  primary key `id = BuiltInAssetClassId.CASH`. Cash is excluded from TOML
  config and can never be disabled. Bank portion values attribute 100% to Cash
  in G-OP-7 actual-allocation calculations. Spec updated in data-requirements
  and service-operations.

- **U-4 resolved — $0 total value → 0% actual for all rows.**
  When a goal's total allocated value (investments + bank) is $0, Actual%
  is 0% for all asset class rows; Difference displays as `$0 ( 0%)`.

## Uncertainties

*(All resolved — see Decisions Made)*

## Handoff Notes

### Files Changed

| File | Change |
|---|---|
| `src/personal_finance/domain/asset_class.py` | Added `BuiltInAssetClassId(IntEnum)` with `CASH = 1` |
| `config.toml` | Removed "Cash" from `asset_classes.names`; added explanatory comment |
| `src/personal_finance/db.py` | Seeds Cash with reserved PK `id=1` before TOML classes |
| `src/personal_finance/service/core/goal_service.py` | Added `get_goal_asset_class_targets`, `update_goal_asset_class_targets`, `list_active_asset_classes` |
| `src/personal_finance/service/application/goal_app_service.py` | Added `GoalListItem`, `GoalAllocationRow`, `GoalAllocationData` DTOs; `get_goals_for_allocation_view`, `get_goal_allocation_data`, `update_goal_asset_class_targets` |
| `src/personal_finance/ui/screens/goals.py` | Added `initial_goal_id` to `GoalsListScreen.__init__`; wired F3 → `GoalAllocationView` via `switch_screen` |
| `src/personal_finance/ui/screens/goal_allocation.py` | **New.** `GoalAllocationView` (F-11b) |
| `tests/service/core/test_goal_service.py` | `TestGetGoalAssetClassTargets`, `TestUpdateGoalAssetClassTargets`, `TestListActiveAssetClasses` |
| `tests/service/application/test_goal_app_service.py` | `TestGetGoalsForAllocationView`, `TestGetGoalAllocationData` |

### Spec files updated

- `specs/canonical/03-user-interface/goals.md` — F-8 F3 action, F-11b completely rewritten (F7 save, dirty-flag guard)
- `specs/canonical/01-requirements/data-requirements.md` — Built-in Cash class paragraph added
- `specs/canonical/02-operations/service-operations.md` — G-OP-7 and G-OP-8 expanded

### Key design decisions recorded in code

- `_GoalListPane` uses `Widget.render()` returning Rich `Text` (no child widgets) — avoids async DOM-mutation complexity for a read-only list
- `on_key` in `GoalAllocationView` checks `isinstance(self.focused, _GoalListPane)` to handle Up/Down without message-based dispatch
- `_navigate_if_clean` centralises the dirty-flag ConfirmationDialog pattern used by all three navigate-away paths

---

*This slice-log is a working-artefact specification. It is not actively maintained after the slice is complete.*
