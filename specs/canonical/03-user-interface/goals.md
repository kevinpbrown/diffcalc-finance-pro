## Goals Flows

### Flow F‑8: View Goals
**Goal:** See list of goals with progress.

**Screen:** `GoalsList`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Goals                                                                  │
 ├────────────────────────────────────────────────────────────────────────┤
 │ Name           Goal              Inv. Alloc   Bank Alloc     Difference│
 │ [Rainy day   ] [$ 25,000.00]     [$  20,495]  [  $ 5,005.00]  $  0.00 │
 │ [Vacation    ] [$ 10,000.00]     [$       0]  { $ 10,000.00}  $  0.00 │
 │ [Automobile  ] {  $ 6,829.64}    [$   6,000]  {      $ 0.00}  $829.64 │
 │ [Retirement  ] {     No goal}    [$ 342,000]  {      $ 0.00}      N/A │
 │                                                                        │
 │ [!] Bank accounts are overclaimed by $1,200.00                         │
 ├────────────────────────────────────────────────────────────────────────┤
 │ [Esc] Back  [F2] New Goal  [F3] Allocation View           [F6] Open  [F8] Discard Goal │
 └────────────────────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - `Name`: Editable text input for the goal name.
  - `Goal`: For 'Manual' goals, this is an editable numeric input; `Enter` on a modified field persists the new scalar target. For 'Present value' or 'No target' goals, the field is gold-bordered and read-only, displaying the calculated or placeholder text. Press `F6` when this field is focused to open `GoalValueDialog` (Flow F-9b) in any goal-type state.
  - `Investment allocation`: Gold-bordered read-only input showing the sum of all accounts assigned to the goal (focusable but not editable). Pressing `F6` when this field is focused opens the `SelectAccountsDialog` (Flow F-10).
  - `Bank Account Allocation`: When the goal uses the scalar bank strategy, this is an editable numeric input; `Enter` on a modified field persists the new scalar bank claim. When "Fill difference from bank accounts" is active, the field is gold-bordered and read-only, displaying the auto-calculated amount. Press `F6` when this field is focused to open `BankAccountAllocationDialog` (Flow F-11) in either state.
  - `Difference`: Read-only value calculated as (Investment allocation + Bank Account Allocation − Goal Target). Positive means allocations exceed the goal (surplus); negative means allocations fall short (deficit). Displayed as N/A for 'No target' goals. Positive values are rendered in green; negative values in red.
  - An overclaim warning is displayed at the bottom if the sum of all bank claims exceeds the total available bank balances.

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields within the grid.
- `Enter` on a modified editable field → Persist changes to the goal (name, scalar goal value, or scalar bank claim).
- `F6` (when the Goal field has focus) → Open `GoalValueDialog` (Flow F-9b).
- `F6` (when the Investment Allocation cell has focus) → Open `SelectAccountsDialog` (Flow F-10).
- `F6` (when the Bank Alloc field has focus) → Open `BankAccountAllocationDialog` (Flow F-11).
- `F2` → Open `CreateGoalDialog` (Flow F-9a).
- `F8` → Trigger `ConfirmationDialog` to discard the focused goal row.
- `F3` → Switch to Allocation View (`GoalAllocationView`); the currently focused goal row is passed as the initially selected goal in F-11b.

**Transition:**
- To `CreateGoalDialog` upon pressing `F2`.
- To `GoalValueDialog` upon pressing `F6` on the Goal field.
- To `SelectAccountsDialog` upon pressing `F6` on the Investment Allocation cell.
- To `BankAccountAllocationDialog` upon pressing `F6` on the Bank Alloc field.
- To `ConfirmationDialog` upon pressing `F8`.
- To `GoalAllocationView` upon pressing `F3`; the focused goal row is pre-selected in F-11b.
- To `Dashboard` upon `Esc`.

**Reference:** 
- `G-1` (View Goal Progress)
- `G-2` (Manage Goals)
- `G-3` (Allocate Assets to Goals)
- `G-4` (Manage Bank Portion of Goal)

### Flow F‑9a: Create Goal Dialog
**Goal:** Define a new financial goal.

**Screen:** `CreateGoalDialog` (modal)
- **Applicable Screens:** `GoalsList`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────┐
 │ Create Goal                                            │
 ├────────────────────────────────────────────────────────┤
 │ Name: [ Automobile         ]                           │
 │                                                        │
 │ Type: [ Present value ▼ ]                              │
 │                                                        │
 │ Future value:  [$  35,000.00]                          │
 │ Savings start: [  2025-05-01]                          │
 │ Maturity date: [  2030-01-01]                          │
 │ Discount rate: [        5.00] %                        │
 │                                                        │
 │ Current goal:  $ 6,829.64                              │
 │ Monthly pymt:  $   514.86                              │
 │                                                        │
 │                                    [Cancel] [Create]   │
 └────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - Name: Editable text input.
  - Type: Dropdown for 'Manual', 'Present value', or 'No target'.
  - If 'Manual', shows only a `Value` numeric input instead of the PV fields.
  - If 'Present value', shows `Future value`, `Savings start`, `Maturity date`, and `Discount rate` inputs. It dynamically calculates and displays the `Current goal` (based on the session effective date) and the required `Monthly pymt`.
  - If 'No target', no additional fields are shown.

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields.
- `Enter` on `[Create]` → Save the new goal and add to list.
- `Esc` or `Enter` on `[Cancel]` → Close without saving.

**Transition:**
- Returns to `GoalsList` upon completion or cancellation.

**Reference:**
- `G-2` (Manage Goals)

### Flow F‑9b: Edit Goal Value Dialog
**Goal:** Modify the target valuation strategy of an existing goal.

**Screen:** `GoalValueDialog` (modal)
- **Applicable Screens:** `GoalsList`
- **Layout:** Same as `CreateGoalDialog` but excluding the `Name` field at the top, and buttons are `[Cancel] [ Save ]`.

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields.
- `Enter` on `[ Save ]` → Save changes to the goal value strategy.
- `Esc` or `Enter` on `[Cancel]` → Close without saving.

**Reference:**
- `G-2` (Manage Goals)

### Flow F‑10: Select Account(s) Dialog
**Goal:** Allocate one or more investment accounts to a goal.

**Screen:** `SelectAccountsDialog` (modal)
- **Applicable Screens:** `GoalsList`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────┐
 │ Select Account(s)                                      │
 ├────────────────────────────────────────────────────────┤
 │ [ ] Dad's TFSA                 $ 100,000.00            │
 │ [x] Mom's RRSP                 $ 100,000.00            │
 │ [-] Dad's RRSP (Rainy day)     $ 120,495.00            │
 │                                                        │
 │                                    [Cancel] [ Save ]   │
 └────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - A scrollable list of all investment accounts.
  - Checkboxes denote selection.
  - Accounts already allocated to another goal are grayed out (shown with `[-]`), cannot be selected, and are skipped during keyboard navigation.

**Actions:**
- `Up` / `Down` → Highlight accounts (blocked accounts are skipped).
- `Space` or `Enter` (when the list is focused) → Toggle selection of the highlighted account.
- `Enter` on `[ Save ]` → Save changes to the goal's `allocatedAccounts`.
- `Esc` or `Enter` on `[Cancel]` → Close without saving.

**Reference:**
- `G-3` (Allocate Assets to Goals)

### Flow F‑11: Bank Account Allocation Dialog
**Goal:** Configure how a goal claims from the bank accounts.

**Screen:** `BankAccountAllocationDialog` (modal)
- **Applicable Screens:** `GoalsList`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────┐
 │ Bank Account Allocation                                │
 ├────────────────────────────────────────────────────────┤
 │ [x] Fill difference from bank accounts                 │
 │                                                        │
 │                                    [Cancel] [ Save ]   │
 └────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - Contains a single checkbox. If checked, the goal uses the `GoalBankPortionAutoFill` strategy. If unchecked, it uses `GoalBankPortionScalar`.

**Actions:**
- `Space` or `Enter` (when the toggle row is focused) → Toggle the checkbox.
- `Tab` / `Shift+Tab` → Navigate fields.
- `Enter` on `[ Save ]` → Save changes.
- `Esc` or `Enter` on `[Cancel]` → Close without saving.

**Reference:**
- `G-4` (Manage Bank Portion of Goal)

### Flow F‑11b: Goal Allocation View
**Goal:** Define and compare target asset allocations against actuals for a specific goal.

**Screen:** `GoalAllocationView`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Goal Allocations                                                       │
 ├───────────────────────┬────────────────────────────────────────────────┤
 │ Goals                 │ Retirement Asset Allocation                    │
 │  Rainy day            │                                                │
 │  Vacation             │ Name             Target Actual $  Actual %    Difference │
 │  Automobile           │ Cash             [  1]%   $3,420      3%  +$6,840 (+ 2%) │
 │ >Retirement       [!] │ Fixed Income     [ 20]%  $61,560     18%  -$6,840 (- 2%) │
 │                       │ US Equity        [ 50]% $153,900     45% -$17,100 (- 5%) │
 │                       │ Canadian Equity  [ 20]%  $75,240     22%  +$6,840 (+ 2%) │
 │                       │ European Equity  [ 10]%  $27,360      8%  -$6,840 (- 2%) │
 │                       │ Emerging Equity  [  5]%  $13,680      4%  -$3,420 (- 1%) │
 │                       │ Other            [  0]%       $0      0%           —     │
 │                       │ Total            106%   $342,000                         │
 │                       │                                                │
 │                       │ [!] Target percentages sum to 106% (max 100%). │
 ├───────────────────────┴────────────────────────────────────────────────┤
 │ [Esc] Back  [F3] Summary View  [F7] Save Changes                       │
 └────────────────────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - 33/67 split layout.
  - **Left pane (Goals List):** Read-only navigable list of all goals. A `[!]` indicator appears next to any goal whose target percentages sum to greater than 100%. The `>` cursor denotes the currently selected goal.
  - **Right pane (Asset Allocation):** Displays all active `AccountAssetClass`es for the selected goal.
    - `Target`: Editable numeric input for the target percentage. Changes are held in memory until `F7` is pressed; no data is written on every keystroke. Pressing `Enter` advances focus to the next `Target%` field (application-wide convention — same as `Tab`).
    - `Actual $`: The dollar amount for this asset class — computed as `actual_percent × total_value`. Formatted as a whole-dollar amount (e.g. `$3,420`). Always shown; $0 when total value is zero. Displayed before `Actual %` to mirror the order in the Difference column (`$` then `%`).
    - `Actual %`: Calculated percentage based on the current values of allocated investments and bank portions (bank portions always count as Cash). When the goal's total allocated value is $0, displays 0% for all rows. Always shown in the standard foreground colour.
    - **Totals row**: Appears below the asset-class rows. Shows the sum of all `Target %` inputs (live, updates as inputs change) and the sum of all `Actual $` values (= `total_value`, fixed for the current data load). `Actual %` (always 100%) and `Difference` are not summed as they provide no additional information.
    - `Difference`: `(actual% − target%) × total_value` for the monetary component and `actual% − target%` for the percentage component. Format: `+$1,234 (+ 5%)` (positive = actual exceeds target) or `-$1,234 (- 5%)` (negative = actual falls short). When total_value is $0, displays `$0 ( 0%)` for all rows. Rows with a 0% target display a dash (`—`) instead of a computed value. Positive values are rendered in green; negative values in red.
    - The over-100% warning and the `[F7] Save Changes` footer shortcut are computed live: the warning appears whenever the sum of in-memory Target% values exceeds 100%; `[F7]` appears whenever any Target% value differs from its persisted state.
    - If target percentages exceed 100%, a full explanation warning appears below the table and `F7` is blocked until the sum is brought to ≤ 100%.

**Actions:**
- `Up` / `Down` (when focus is on the left pane) → Navigate goals (with dirty-check); focus stays in the left pane.
- `Enter` (when focus is on the left pane) → Move focus to the first `Target%` input in the right pane.
- `Tab` / `Shift+Tab` → Move focus between the left pane and the right pane.
- `Up` / `Down` (when focus is on the right pane) → Navigate between `Target%` input cells.
- Editing a `Target%` field → Changes are held in memory only; `[F7]` appears in the footer when any field differs from its persisted value (dirty flag set).
- `F7` (when changes are pending and sum ≤ 100%) → Persist all in-memory Target% values for the selected goal via G-OP-8. Clears the dirty flag; `[F7]` disappears from the footer after a successful save.
- `F7` (when sum > 100%) → Blocked; show a validation error notification.
- `F3` (when not dirty) → Switch back to the Summary View (`GoalsList`); the goal selected in F-11b is pre-focused in F-8.
- `F3` (when dirty) → Prompt "Discard unsaved changes?" via `ConfirmationDialog`; on confirm, discard edits and switch to `GoalsList` with the selected goal pre-focused; on cancel, remain in F-11b.
- `Esc` (when not dirty) → Switch back to the Summary View (`GoalsList`) — same behaviour as `F3`. `Esc` is treated as "back", not "escape to root".
- `Esc` (when dirty) → Prompt "Discard unsaved changes?" via `ConfirmationDialog`; on confirm, discard edits and switch to `GoalsList` with the selected goal pre-focused; on cancel, remain in F-11b.

**Transition:**
- To `GoalsList` upon pressing `F3` or `Esc` (after confirming discard if dirty); the goal selected in F-11b is pre-focused in F-8.
- **Entry from F-8:** The goal that was focused in F-8 when `F3` was pressed is initially selected in F-11b.

**Reference:**
- `G-5` (Manage Goal Asset Class Targets)

