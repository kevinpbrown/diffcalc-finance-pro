/work-on-slice @specs/work-product/slice-logs/2026-06-09-cash-flow.md 

This is a Phase 2 (Implementation) session. 

Read specs/canonical/03-user-interface/cash-flow.md (flows F-13 and F-13a) before starting.
Read src/personal_finance/ui/README.md.

## What to build

Create src/personal_finance/ui/screens/cash_flow_expenses.py containing:

### CashFlowExpensesView (F-13)
A TwoPaneScreen subclass (see base.py for the pattern used by CashFlowPersonProfileView 
in cash_flow.py).

Left pane: `_CashFlowNavPane` (import from cash_flow.py) with "Expenses" active. 
Navigating to a person → switch_screen to CashFlowPersonProfileView with that profile_id.
Navigating to "Household Cash Flow" → switch_screen to HouseholdCashFlowReportView.
Esc → switch_screen to DashboardScreen.

Right pane: grouped expense list. Each group has a header label (Home / Auto / Other) 
followed by expense rows. Each expense row is a horizontal widget containing:
- A Static label (the name, non-focusable, left-aligned, 1fr width)
- A MoneyInput for the amount (right-aligned, 20-wide)

The right pane is a VerticalScroll. It does NOT include the summary table.

Summary table: a FIXED, non-scrolling widget mounted below the left/right pane split and 
above the SplitFooter. It spans the full screen width. It shows the cross-tab of 
Source × Frequency with row and column totals (see F-13 layout mockup in the spec). 
Use a Static or a custom widget; it must update whenever an expense amount is saved.

BINDINGS:
- Esc → go to Dashboard
- F2 → open ExpenseDialog (create, Home)
- F3 → open ExpenseDialog (create, Auto)
- F4 → open ExpenseDialog (create, Other)
- F7 → open ExpenseDialog (edit) — contextual, right-aligned
- F8 → ConfirmationDialog to discard — contextual, right-aligned

check_action: F7 and F8 are only active when an amount MoneyInput on an expense row has focus.

On Enter in any amount MoneyInput: parse and call update_household_expense with the new 
amount only (name, source, frequency unchanged — they are edited only via the dialog).

### ExpenseDialog (F-13a) — in the same file or cash_flow_dialogs.py
ModalDialogMixin + ModalScreen. Fields: Name (TextInput), Amount (MoneyInput), 
Source (AppSelect: Bank / Credit Card / Other), Frequency (AppSelect: Regular / Irregular).
- Create mode: title "New [Home|Auto|Other] Expense", [Cancel] [Create]
- Edit mode: title "Edit Expense", pre-populated, [Cancel] [Save]
- Dismisses with the new/updated expense_id (int) or None on cancel.

Run `.venv/bin/pytest`, then `.venv/bin/personal-finance` and navigate to Cash Flow → 
Expenses to verify the full flow: create, edit via F7, amount edit in-place, discard.

--

Navigating to the Expenses item in the Cash Flow module is currently crashing with:

│   4242 │   def _render_content(self) -> None:                                                                                          │
│   4243 │   │   """Render all lines."""                                                                                                 │
│   4244 │   │   width, height = self.size                                                                                               │
│ ❱ 4245 │   │   visual = self._render()                                                                                                 │
│   4246 │   │   strips = Visual.to_strips(self, visual, width, height, self.visual_style)                                               │
│   4247 │   │   self._render_cache = _RenderCache(self.size, strips)                                                                    │
│   4248 │   │   self._dirty_regions.clear()                                                                                             │
│                                                                                                                                        │
│ ╭────────────────────── locals ───────────────────────╮                                                                                │
│ │ height = 7                                          │                                                                                │
│ │   self = _ExpenseSummaryWidget(id='cfexpr-summary') │                                                                                │
│ │  width = 136                                        │                                                                                │
│ ╰─────────────────────────────────────────────────────╯                                                                                │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
TypeError: _ExpenseSummaryWidget._render() missing 1 required positional argument: 'data'

--

Updates:

- When Expenses is selected on the left-hand side, the focus is moving over to the right-hand side automatically. As is the convention elsewhere, please keep focus on the left-hand side until the user tabs over to the right-hand side. Please document this behaviour in the repo's harnesses so this is applied to future features.
- F2, F3 and F4 aren't doing anything. They should be opening the new expense dialog (Flow F-13a)
- Could you please highlight the far-right Totals column the same white as the bottom Totals row?

---

/work-on-slice @specs/work-product/slice-logs/2026-06-09-cash-flow.md

This is a Phase 2 (Implementation) session. Read specs/canonical/03-user-interface/cash-flow.md (flows F-14 and F-15) before starting. Read src/personal_finance/ui/README.md.

## What to build

Create src/personal_finance/ui/screens/cash_flow_report.py containing:

### HouseholdCashFlowReportView (F-14)
A TwoPaneScreen subclass (same pattern as CashFlowPersonProfileView).

Left pane: `_CashFlowNavPane` with "Household Cash Flow" active. Navigation to person or 
Expenses follows the same switch_screen pattern as the other cash flow views.

Right pane: a VerticalScroll with all report lines as Static widgets (read-only text), 
except the automated contribution rows, which use GoldBorderDisplay widgets (gold-bordered, 
focusable, not editable — the same widget used in balance_sheet.py for investment balances). 
Pressing F6 when a GoldBorderDisplay contribution field is focused opens 
AutomatedContributionDialog in edit mode.

See the F-14 layout mockup in the spec for the exact line structure (gross income, RRSP 
deductions, net income, average expenses, contribution list, totals, bonus, goal summary).

BINDINGS:
- Esc → go to Dashboard
- F2 → open AutomatedContributionDialog (create)
- F6 → open AutomatedContributionDialog (edit) — contextual, right-aligned
- F8 → ConfirmationDialog to discard focused contribution — contextual, right-aligned

check_action: F6 and F8 are only active when a GoldBorderDisplay contribution field has focus.
Derive contribution_id from the widget id (e.g., "contrib-{id}").

### AutomatedContributionDialog (F-15) — in the same file or cash_flow_dialogs.py
ModalDialogMixin + ModalScreen. Fields: Name (TextInput), Amount (MoneyInput), 
From account (AppSelect populated from get_account_options()), 
To account (AppSelect populated from get_account_options()), 
Goal (AppSelect populated from get_goal_options()). All fields required.
- Create mode: title "Automated Contribution", [Cancel] [Create]
- Edit mode: pre-populated, [Cancel] [Save]
- Dismisses with contribution_id (int) or None on cancel.

After create/edit/discard, reload the report view data and repaint.

Run `.venv/bin/pytest`, then `.venv/bin/personal-finance` and navigate to Cash Flow → 
Household Cash Flow to verify the full flow: report renders correctly, F2 creates a 
contribution, F6 edits it, F8 discards it.

--

Updates:
- Hide the "Automated Contributions:" line if there are none
- Align the dollar signs for all line items (see attached)
- Automated contribution names should be vertically set to the middle (currently aligned to the top). See attached. It looks like we're already doing this in the Balance Sheet, but all flows under Cash Flow appear to be affected by this. Please fix it in each of the three Cash Flow flows.
- Let's specify "Amount per month" in the Automated Contribution dialog so that's clear. Please update the dialog and the spec.
- Automated contribution account option should be filtered in the dropdown: "From account" should list only current bank accounts; "To account" should only list investment accounts. We don't need that captured in the domain model -- these are captured for visibility and reporting (so you can run a report to ensure that your goals are properly funded w.r.t. their defined targets), there aren't any functional implications. Filtering in the UI is enough, although I'm still undecided on whether it should be enforced in the service layer. I'm not a fan of something being constrained with UI filters only, but I also don't see a lot of value in the extra service logic (other than code visibility). What's the pros/cons? Keep it just to the UI filtering for this prompt but provide me with an analysis so I can make a call in the next prompt.

--

At this point, it appears that the Cash Flow vertical slice is complete. Please check that we didn't miss anything. If there's nothing left, then please close the slice.

---

