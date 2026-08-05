## Cash Flow Flows

### Flow F‑12: Cash Flow Person Profile View
**Goal:** Define and edit the annual income profile for a specific person.

**Screen:** `CashFlowPersonProfileView`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Cash Flow                                                   2026-05-12 │
 ├───────────────────────┬────────────────────────────────────────────────┤
 │ Profiles              │ Alice Profile                                  │
 │ >Alice                │                                                │
 │  Bob                  │ Gross income                 [$    120,000.00] │
 │ ───────────────────── │ Net income                   [$     85,000.00] │
 │  Expenses             │ ────────────────────────────────────────────── │
 │  Household Cash Flow  │ Gross bonus                  [$     10,000.00] │
 │                       │ Net bonus                    [$      6,500.00] │
 │                       │ ────────────────────────────────────────────── │
 │                       │ Auto RRSP and Match Goal     [Retirement   ▼ ] │
 │                       │ Auto RRSP contribution       [$      5,000.00] │
 │                       │ Auto RRSP match              [$      5,000.00] │
 ├───────────────────────┴────────────────────────────────────────────────┤
 │                                                                        │
 └────────────────────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - 33/67 split layout.
  - **Left pane (Navigation):** Read-only list of all `Person` profiles at the top. A line separator divides it from the `Expenses` and `Household Cash Flow` sections at the bottom. Clicking an item navigates to it (same effect as keyboard selection).
  - **Right pane (Profile Inputs):** Displays the editable income and bonus numbers as well as automated RRSP contributions and goal assignments for the selected person.
    - The "Auto RRSP and Match Goal" dropdown appears first. Both RRSP money inputs are **disabled** until a goal is selected.
    - When the goal dropdown closes with a non-null selection, focus moves to "Auto RRSP contribution" (fires on both value-change and same-item re-select).
    - "Auto RRSP match" remains disabled until "Auto RRSP contribution" is greater than zero.
    - Clearing the goal dropdown zeroes and disables both money inputs.
  - **Focus discipline:** Navigating between profiles via `Up` / `Down` or mouse click **never** moves focus out of the left pane. Focus only crosses to the right pane when the user presses `Tab`, `Enter` (on the left pane), or selects a goal from the dropdown.

**Actions:**
  - `Up` / `Down` (when focus is on the left pane) → Navigate between Person profiles, Expenses, and Household Cash Flow. Focus stays in the left pane.
  - Mouse click (on the left pane) → Navigate directly to the clicked item. Focus stays in the left pane.
  - `Enter` (when focus is on the left pane and a Person is selected) → Move focus to the first right-pane input field.
  - `Tab` / `Shift+Tab` → Move focus between the left pane and the input fields on the right pane.
  - `Enter` on a modified field → Persist changes to the `PersonalCashFlowProfile`.
  - `Esc` (when not editing) → Navigate back to `Dashboard`.

**Transition:**
  - To `CashFlowExpensesView` (Flow F-13) if `Expenses` is selected.
  - To `HouseholdCashFlowReportView` (Flow F-14) if `Household Cash Flow` is selected.

**Reference:**
- `CF-1` (Manage Cash Flow Profiles)

### Flow F‑13: Cash Flow Expenses View
**Goal:** View and manage regular and irregular household expenses.

**Screen:** `CashFlowExpensesView`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Cash Flow                                                   2026-05-12 │
 ├───────────────────────┬────────────────────────────────────────────────┤
 │ Profiles              │ Expenses                                       │
 │  Alice                │ Name                              Amount       │
 │  Bob                  │ Home                                           │
 │ ───────────────────── │  Mortgage                   [$      2,000.00]  │
 │ >Expenses             │  Property Tax               [$        300.00]  │
 │  Household Cash Flow  │ Auto                                           │
 │                       │  Gas                        [$        150.00]  │
 │                       │  Car Insurance              [$        100.00]  │
 │                       │ Other                                          │
 │                       │  Groceries                  [$        600.00]  │
 │                       │  Vacation Fund              [$        200.00]  │
 ├───────────────────────┴────────────────────────────────────────────────┤
 │ Summary (Monthly)                                                      │
 │              Regular    Irregular       Total                          │
 │ Bank        $ 2,400.00  $   200.00  $ 2,600.00                         │
 │ Credit Card $   750.00  $     0.00  $   750.00                         │
 │ Other       $     0.00  $     0.00  $     0.00                         │
 │ Total       $ 3,150.00  $   200.00  $ 3,350.00                         │
 ├────────────────────────────────────────────────────────────────────────┤
 │ [Esc] Back  [F2] New Home  [F3] New Auto  [F4] New Other  [F7] Edit Expense  [F8] Discard │
 └────────────────────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - **Left pane:** Navigation with `Expenses` currently active.
  - **Right pane (scrollable):** List of all active `HouseholdExpense` items, grouped by classification (`Home`, `Auto`, `Other`). Expense names are **static labels** — not directly editable in-place. Only the monthly `Amount` field is editable in-place. Source, Frequency, and Name are edited via the `ExpenseDialog` (Flow F-13a), opened with `F7`.
  - `F7` is a **contextual** footer binding (right-aligned): it appears only when focus is on an expense row's amount field.
  - **Summary table (fixed):** Pinned at the bottom of the right pane, above the footer. Cross-tabulates `Source` (Bank, Credit Card, Other) by `Frequency` (Regular, Irregular), with row and column totals. Updates whenever an expense amount is saved.

**Actions:**
  - `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate between amount fields in the table.
  - `Enter` (when focus is on the left pane and `Expenses` is selected) → Move focus to the first expense amount field.
  - `Enter` on a modified amount field → Persist the new amount for the `HouseholdExpense`.
  - `F7` (when any expense amount field has focus) → Open `ExpenseDialog` (Flow F-13a) in edit mode for the focused expense.
  - `F2` → Open `ExpenseDialog` (Flow F-13a) in create mode, pre-set to the `Home` category.
  - `F3` → Open `ExpenseDialog` (Flow F-13a) in create mode, pre-set to the `Auto` category.
  - `F4` → Open `ExpenseDialog` (Flow F-13a) in create mode, pre-set to the `Other` category.
  - `F8` → Trigger `ConfirmationDialog` to discard the currently focused expense row.
  - `Esc` (when not editing) → Navigate back to `Dashboard`.

**Transition:**
  - To `ExpenseDialog` (Flow F-13a) upon pressing `F2`, `F3`, `F4`, or `F7`.
  - To `ConfirmationDialog` (Flow F-25) upon pressing `F8`.

**Reference:**
- `CF-2` (Manage Household Expenses)

### Flow F‑13a: Create / Edit Expense Dialog
**Goal:** Add a new household expense or edit an existing one.

**Screen:** `ExpenseDialog` (modal)
- **Applicable Screens:** `CashFlowExpensesView`
- **Layout (create mode):**
```text
 ┌────────────────────────────────────────────────────────┐
 │ New Home Expense                                       │
 ├────────────────────────────────────────────────────────┤
 │ Name:       [ Mortgage                   ]             │
 │ Amount:     [$                  2,000.00 ]             │
 │ Source:     [ Bank                      ▼]             │
 │ Frequency:  [ Regular                   ▼]             │
 │                                                        │
 │                                    [Cancel] [Create]   │
 └────────────────────────────────────────────────────────┘
```
- **Layout (edit mode):**
```text
 ┌────────────────────────────────────────────────────────┐
 │ Edit Expense                                           │
 ├────────────────────────────────────────────────────────┤
 │ Name:       [ Mortgage                   ]             │
 │ Amount:     [$                  2,000.00 ]             │
 │ Source:     [ Bank                      ▼]             │
 │ Frequency:  [ Regular                   ▼]             │
 │                                                        │
 │                                    [Cancel] [  Save ]  │
 └────────────────────────────────────────────────────────┘
```
- **Field descriptions:**
  - *Name*: free-text label for the expense.
  - *Amount*: monthly dollar amount.
  - *Source*: Bank, Credit Card, or Other.
  - *Frequency*: Regular or Irregular.
- **Titles and buttons:**
  - Create mode: title "New [Home | Auto | Other] Expense" (category derived from the function key pressed), buttons `[Cancel]` `[Create]`.
  - Edit mode: title "Edit Expense", buttons `[Cancel]` `[Save]`.
  - All four fields are editable in both modes.

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields.
- `Enter` on `[Create]` → Save the new expense, close dialog, and refresh the expense list.
- `Enter` on `[Save]` → Persist changes, close dialog, and refresh the expense list. Focus returns to the amount field of the edited row.
- `Esc` or `Enter` on `[Cancel]` → Close without saving.

**Reference:**
- `CF-2` (Manage Household Expenses)

### Flow F‑14: Household Cash Flow Report View
**Goal:** View a projected monthly and annual cash flow summary.

**Screen:** `HouseholdCashFlowReportView`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Cash Flow                                                   2026-05-12 │
 ├───────────────────────┬────────────────────────────────────────────────┤
 │ Profiles              │ Household Cash Flow                            │
 │  Alice                │                                                │
 │  Bob                  │ Total monthly gross income         $ 10,000.00 │
 │ ───────────────────── │   Less Automated RRSP for Alice    $   (833.33)│
 │  Expenses             │   Less taxes & other               $ (2,083.34)│
 │ >Household Cash Flow  │ Total monthly net income           $  7,083.33 │
 │                       │ ────────────────────────────────────────────── │
 │                       │ Less:                                          │
 │                       │   Average monthly expenses         $  3,350.00 │
 │                       │   Automated contributions:                     │
 │                       │    Dad's TFSA              [$        800.00]   │
 │                       │    Mom's TFSA              [$        800.00]   │
 │                       │    Car replacement         [$        300.00]   │
 │                       │    Education               [$        500.00]   │
 │                       │                                                │
 │                       │ Total monthly retained             $  1,333.33 │
 │                       │ ────────────────────────────────────────────── │
 │                       │ Total annual retained              $ 16,000.00 │
 │                       │ Total net bonus                    $  6,500.00 │
 │                       │                                                │
 │                       │ Total annual retained              $ 22,500.00 │
 │                       │   (17.3% of gross family income)               │
 │                       │ ────────────────────────────────────────────── │
 │                       │ Goal Contributions (Annualized)                │
 │                       │ Goal                   Amount                  │
 │                       │ Retirement         $ 29,200.00                 │
 │                       │ Car replacement    $  3,600.00                 │
 │                       │ Education          $  6,000.00                 │
 ├───────────────────────┴────────────────────────────────────────────────┤
 │ [Esc] Back  [F2] Add Contribution                [F6] Open  [F8] Discard Contribution │
 └────────────────────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - **Left pane:** Navigation with `Household Cash Flow` currently active.
  - **Right pane (Report):** A read-only report presenting aggregated values:
    - Monthly Gross income, followed by read-only deduction lines that fully reconcile gross to
      net: one "Less Automated RRSP for \<Name\>" line per `Person` whose
      `auto_rrsp_deducted > 0` (amount = `(auto_rrsp_deducted + rrsp_matched) / 12`), then a
      single "Less taxes & other" line for the implicit remainder (`gross_monthly − Σ RRSP lines − net_monthly`), then Monthly Net income. These lines are display-only — RRSP
      contributions are already reflected in the user-entered net income (net = bank deposit)
      and are **not** subtracted again in the "Less:" section below.
    - Subtractions for Average Monthly Expenses (from the Expenses view) and Automated contributions.
    - A list of Automated contributions displayed as **gold-bordered read-only inputs** (focusable but not editable). Pressing `F6` when one of these fields is focused opens the `AutomatedContributionDialog` (Flow F-15) for editing. `F6` is a **contextual** footer binding (right-aligned): it appears only when focus is on a contribution field.
    - Computed Total Monthly Retained and Total Annual Retained.
    - Total Net Bonus and Final Total Annual Retained including bonus, displaying the percentage of gross family income this represents.
    - Summary of Goal contributions, tabulating assigned goals from the `PersonalCashFlowProfile` automated RRSP fields and all `AutomatedContribution` records (annualized).

**Actions:**
  - `Up` / `Down` (when focus is on the left pane) → Navigate between Person profiles, Expenses, and Household Cash Flow.
  - `Tab` / `Shift+Tab` → Move focus between the left pane and the gold-bordered contribution fields.
  - `Enter` (when focus is on the left pane and `Household Cash Flow` is selected) → Move focus to the first gold-bordered contribution field.
  - `F6` (when a gold-bordered contribution field has focus) → Open `AutomatedContributionDialog` (Flow F-15) for editing.
  - `F2` → Open `AutomatedContributionDialog` (Flow F-15) to create a new contribution.
  - `F8` → Trigger `ConfirmationDialog` to discard the automated contribution currently focused.
  - `Esc` → Navigate back to `Dashboard`.

**Reference:**
- `CF-3` (View Cash Flow Projection)

### Flow F‑15: Automated Contribution Dialog
**Goal:** Add or edit an automated cash flow contribution.

**Screen:** `AutomatedContributionDialog` (modal)
- **Applicable Screens:** `HouseholdCashFlowReportView`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────┐
 │ Automated Contribution                                 │
 ├────────────────────────────────────────────────────────┤
 │ Name:               [ Dad's TFSA               ]       │
 │ Amount per month:   [$                  800.00 ]       │
 │ From account:       [ Tangerine Checking     ▼ ]       │
 │ To account:         [ Dad's TFSA Inv         ▼ ]       │
 │ Goal:               [ Retirement             ▼ ]       │
 │                                                        │
 │                                    [Cancel] [ Save ]   │
 └────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - `Name`: Editable text input.
  - `Amount per month`: Editable numeric input — the monthly transfer amount.
  - `From account`: Dropdown of active **bank accounts** only (source of funds).
  - `To account`: Dropdown of active **investment accounts** only (destination).
  - `Goal`: Dropdown of all available goals.
  - The UI enforces that all fields are required before saving.

**Actions:**
  - `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields.
  - `Enter` on `[ Save ]` → Save changes to the `AutomatedContribution` and update the view.
  - `Esc` or `Enter` on `[Cancel]` → Close without saving.

**Reference:**
- `CF-4` (Manage Automated Contributions)

