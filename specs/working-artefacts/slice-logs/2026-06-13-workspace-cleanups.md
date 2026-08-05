# Slice: Workspace Cleanups

**Date:** 2026-06-13
**Status:** Complete

## Description

Cross-cutting quality pass on the UI layer and test suite before continuing the Cash Flow
module. Three focus areas:

1. **Input navigation consistency** — The convention (Enter advances to the next field;
   Up/Down also navigate) must be baked into reusable widget components so it applies
   everywhere without per-screen follow-up work.

2. **Field placement rationalisation** — Fields that users rarely change are currently
   presented inline, forcing them to Tab through every time. Move such fields into the same
   creation/edit dialogs already used for that entity, matching the pattern established
   elsewhere in the app.

3. **Test coverage audit** — Confirm the service and domain layers meet the ≥ 80 % line
   coverage threshold required by the technical charter before the Cash Flow slice
   resumes.

This slice is a pause from the Cash Flow slice to fix structural issues that would otherwise
accumulate tech-debt across every future screen.

## Specification References

### UI Flows to Implement

Existing flows updated in place:
- **F-4** (Balance Sheet Summary) — account names → static labels, `F7` contextual edit binding
- **F-5** (Account Dialog) — extended to cover edit mode
- **F-13** (Expenses View) — amount-only inline editing, full-width fixed summary, `F7` contextual edit binding, F2/F3/F4 now open dialog
- **F-14** (Household Cash Flow Report) — gold-border F6 pattern for contributions, `Ins` → `F2`

New flow introduced:
- **F-13a** (`ExpenseDialog`) — Create / Edit Expense Dialog

### Operations to Implement

No new service operations are introduced.

## Dependencies

- [2026-06-09-cash-flow.md](2026-06-09-cash-flow.md) — the in-progress slice this work
  unblocks; partially implemented screens are the primary subject of item 2.
- [2026-06-05-goal-allocation-view.md](2026-06-05-goal-allocation-view.md) — established
  reusable widget patterns (`ModalDialogMixin`, `RightAlignedNumericInput`) that this slice
  extends.

## ADRs

### Referenced

- None yet identified.

### Created

- None yet.

## Decisions Made

- **F-4 account names become static labels.** Only the balance field remains editable in-place. `F7` is a new contextual binding (right-aligned in footer) that opens `AccountCreationDialog` in edit mode when any account row balance field has focus.
- **F-5 extended to cover edit mode.** Same dialog, title changes to "Edit [Asset|Liability]", `[Create]` becomes `[Save]`, and the Nature field (Simple vs Investment) is rendered as a read-only label — switching account type after creation is not supported.
- **F-13 expense rows simplified.** Only the Amount field remains editable in-place. Name becomes a static label; Source and Frequency are no longer shown in the row — they are only accessible via the new `ExpenseDialog` (F-13a). `F7` contextual binding opens the edit dialog.
- **F-13 creates now go through a dialog.** `F2`/`F3`/`F4` open the new `ExpenseDialog` in create mode (pre-set to Home/Auto/Other respectively) rather than inserting a row with defaults.
- **F-13 summary table is full-width and fixed.** The summary section is pinned below the left/right pane split, spanning the full screen width, and is not part of the scrollable right pane.
- **F-14 contribution fields use the gold-border F6 pattern.** The `[$800|...]` compound widget is replaced by a standard gold-bordered read-only input; `F6` opens the `AutomatedContributionDialog`.
- **F-14 add contribution keybinding changed from `Ins` to `F2`.**

## Uncertainties

- [x] **U-1** — Resolved: see Decisions Made above.
- [x] **U-2** — Resolved: **Enter → each widget owns it; Up/Down → screens and `ModalDialogMixin` own it.**
  - `TextInput` and `RightAlignedNumericInput` fire `screen.focus_next()` on `Input.Submitted`.
  - `AppSelect`, `AppCheckbox`, and `AppRadioSet` each intercept Enter in `_on_key` and call `screen.focus_next()`.
  - Up/Down remains in the screen's `on_key` and `ModalDialogMixin.on_key` because `AppRadioSet` claims Up/Down internally for within-group navigation, and `AppSelect` uses Down to open the dropdown — neither can redirect those keys to focus navigation at the widget level.
  - The Up/Down handlers inside `TextInput.on_key` and `RightAlignedNumericInput.on_key` are therefore redundant (the screen/mixin would catch those events if the widget didn't stop them), but are harmless and left in place for clarity.
- [x] **U-3** — Resolved: baseline was 83.17%. Tests added for `cash_flow_service`, `cash_flow_app_service`, and the uncovered paths in `goal_app_service`. Coverage reached **93.83%** (419 tests passing), well above the 80% threshold mandated by the charter.
- [x] **U-4** — Resolved: the implementation already has an `Owner(s)` checkbox list (one per `Person`). The spec had drifted; F-5 wireframes updated to include it in both create and edit modes.

## Handoff Notes

- **Test coverage is healthy.** The service and domain layers are at 93.83% overall. The only intentionally uncovered paths are: the holding asset-class distribution loop in `goal_app_service.get_goal_allocation_data` (requires an `ExactHolding` with `HoldingAssetClassAllocation` fixtures — complex to set up, low risk), `dashboard_service.py` (thin wrapper, not tested in isolation), and `__main__.py` / `db.py` (entry-point bootstrapping).
- **Two bugs fixed in this slice** (not in the original scope, addressed opportunistically):
  - `DashboardScreen`: "Amount Left to Invest" now refreshes via `on_screen_resume` whenever the user returns from a sub-screen.
  - `InvestmentEditorScreen`: After adding a holding via `AddHoldingDialog`, focus is restored to the widget that was active before the dialog opened, rather than jumping to the top of the list.
- **Navigation architecture invariant established (U-2).** Follow-on screens must not add Up/Down handling to `AppRadioSet`, `AppSelect`, or `AppCheckbox` — those cases are covered by the screen/mixin layer. New text-input subclasses of `RightAlignedNumericInput` or `TextInput` inherit Enter-advance automatically and need no extra Up/Down code.
- **Resume the Cash Flow slice.** This slice was a planned pause before continuing [2026-06-09-cash-flow.md](2026-06-09-cash-flow.md). The blocking structural issues (navigation consistency, field placement, test coverage) are resolved.

---

*This slice-log is a working-artefact specification. It is not actively maintained after the slice is complete.*
