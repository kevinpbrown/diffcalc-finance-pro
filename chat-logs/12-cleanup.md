/start-slice @specs/work-product/slice-logs/2026-06-09-cash-flow.md workspace-cleanups 

We are not done the Cash Flow module's slice yet, but we need to pause it so that we can take care of some workspace cleanup, particularly in the user interface. 

There are few issues we will address:
- Reuse and consistency between Textual data inputs is suboptimal, particularly between different modules. Our convention to press Enter to proceed to the next field or use Up/Down to navigate is still not being applied with the first prompt (I have to constantly call it out as a follow-up task). We will bake this into our reusable components so that's no longer a problem.
- The UI is requiring users to Enter through a number of fields that will rarely change. We will want to move those to a dialog, likely the same dialogs that are currently only being used for creation. This will require updates to the specs and code.
- We will want to explicitly check that the test coverage is optimal.

Please start the slice log and we'll begin on our first item after that.

--

Let's start by identifying all common input functionality across the modules. That is, NumericInput, MoneyInput, PercentInput, DateInput, Select, etc. We want those components to be reused across the entire application so that every modules behaves consistently. 

For example:
- The Goals view formats dollar values with a dollar sign. The Balance Sheet view formats with commas but no dollar sign. After editing, the Goals view loses all formatting until the view is refreshed. After editing, the Balance Sheet view will always reformat with commas. The Cash Flow module does none of this.
- The dropdown is also inconsistent. Some places, pressing Enter shifts focus always (you have to press Space to open it) -- the Goals dialog works like this. Other places it tabs after selecting a value.

Let's start by identifying all the different input types so we have an inventory. Then let's make decisions on all the different possible ways they can work. For example, for money inputs, I'll likely prefer a hybrid of Goals and Balance Sheet: The dollar sign should always be displayed, but left justified if possible. Commas should always be added. And text inputs should always be reformatted after editing is complete.

--

Some bugs:
- Pressing Enter somehow double skips some fields. Pressing Tab or Down does not -- those work fine. I tried an alternate keyboard to make sure it wasn't that (since it's not happening all the time).
- Can we try and make the dollar sign truly left-aligned counter to the right-aligned numeric value? You can see in the screenshot that all the dollar signs are not aligned.
- Dropdowns toward the right of the screen can spill out of view (see second attachment). Can you add sensing logic so that if the dropdown spills out, we change its orientation logs so that it aligns with the opposite side of the stationary dropdown box?

--

What are the investment account gold-bordered F6-to-open components using? Can you left-justify their formatted dollar values in the exact same way? I've attached an image of their current out-of-alignment state.

Could you also adjust the dropdown logic you added so that when it flips the other direction, the alignment is to the opposite edge of the dropdown? I've included a screenshot with green annotation on what I mean.

--

Now the numeric value in the gold-bordered boxes are left-aligned too. Please keep the dollar sign left aligned and the numeric value right-aligned just like you did for the MoneyInput field.

--

Same issue is still persistent: numeric value in the gold-bordered boxes are left-aligned too. Switching to Opus to hopefully put this one to bed.

Desired outcome:  the dollar sign left aligned and the numeric value right-aligned just like you did for the MoneyInput field.

--

There are some checkboxes throughout. Can we centralize that input too. Let's make it consistent with the dropdowns: Enter to progress to the next, Space to toggle.

--

There are also radio button select groups as well. Can they be centralized? Are they currently consistent across the application?

--

I notice that the checkboxes in the Goals dialogs are non-standard. Is there a reason for this? Can we standardize them using standard checkboxes?

--

Can you update the technical charter to make sure all these new standardized inputs are used exclusively in future slices? If a new type of input, or a new behaviour to an existing input is requested, the agent should take a step back and ask whether a new custom component should be introduced or if more configuration should be added to an existing one.

---

/work-on-slice @specs/work-product/slice-logs/2026-06-13-workspace-cleanups.md 

Next, we will clean up some clunkiness in the UI. Please start with the UI specifications and then we'll proceed with any updates to the existing implementation.

- The list of names on the Balance Sheet screen F-4 isn't that useful -- those names rarely change. Also, after creating a new account, there isn't an opportunity to see the metadata associated with it (e.g., owners). So, let's make the account name a static label. Then, whenever an input box for the account row is in focus, an F7 contextual shortcut (right-justified) will appear to edit the account. Pressing F7 will show the create account dialog but in edit mode. All fields should be editable except for the switch from a simple asset to an investment account and vice versa. Let me know if there's anything I'm missing in thinking that through.
- The same situation also exists on F-13: there only the amount needs to be first-class editable on the screen itself. All the other fields can be tucked away on an F7 edit shortcut that reuses a "Create Expense" dialog. We avoided having to introduce that dialog by putting everything on the screen, so that'll need to be introduced in the specs too as a new flow.
- Flow F-14 is completely out-of-date: Ins to add a contribution should be changed to F2. The automated contribution input with the "..." should be switched to the new F6-openable field pattern.
- Please make sure it's clear in Flow F-13 that the expense summary table should be fixed to the bottom of the view and stretch across the whole screen.

--

Regarding the open question: looks like we've let the specs drift (attached is the current implementation). We should add owners to both wireframes in F-5.

--

Do we need to update our functional requirements (Layer 1) or operations (Layer 2) documentation at all for this? In particular, the constraint that the nature of an account is not editable.

--

Could you please analyze what needs to be done in the code and provide me with prompts -- structured into as many separate tasks as you see fit -- to start the process in new context windows? Please start each prompt with the same `work-on-slice` command that started off this window.

---

/work-on-slice @specs/work-product/slice-logs/2026-06-13-workspace-cleanups.md

This is a Phase 2 (Implementation) session. Work on the service-layer portion only — no UI changes.

## Context

The balance sheet account edit dialog (F-5, see specs/canonical/03-user-interface/balance-sheet.md) 
is being added. When F7 is pressed on any account row, the dialog will open pre-populated with 
that account's current metadata and let the user save changes. The service layer needs two things:

1. A way to LOAD full account metadata (name, term classification, nature, simple category / 
   investment registration, current owner IDs) for pre-populating the dialog.
2. A way to SAVE updated metadata (all fields except nature, which is immutable after creation).

## Current State

- `balance_sheet_app_service.py` has `update_account_name(account_id, new_name)` annotated 
  "BS-OP-3 (partial)" — it only updates the name.
- `balance_sheet_service.py` has a matching `update_account_name` at the core layer.
- `AccountSummaryRow` (the DTO used by the balance sheet screen) only carries: account_id, 
  name, balance, is_investment. It has no classification, registration, or owner information.

## What to build

### In `balance_sheet_service.py` (core service):
- Rename `update_account_name` → `update_account_metadata(account_id, name, classification, 
  simple_category, investment_registration, owner_ids)` implementing full BS-OP-3.
  - `classification` is the AccountClassification enum (ASSET_CURRENT, ASSET_LONG_TERM, etc.)
  - `simple_category` is a SimpleAccountCategory (or None for investment accounts)
  - `investment_registration` is an InvestmentRegistration (or None for simple accounts)
  - `owner_ids` is list[int]; must be non-empty
- Add `get_account_detail(account_id)` that returns a new dataclass with all the fields 
  needed to pre-populate the edit dialog.

### In `balance_sheet_app_service.py` (application service):
- Add a `AccountDetail` dataclass (with: account_id, name, is_long_term: bool, is_investment: 
  bool, simple_category: SimpleAccountCategory | None, investment_registration: 
  InvestmentRegistration | None, owner_ids: list[int]).
- Add `get_account_detail(account_id) -> AccountDetail` wrapping the core method.
- Replace `update_account_name` with `update_account_metadata(account_id, name, is_long_term, 
  simple_category, investment_registration, owner_ids)` that maps to the core method 
  (deriving the AccountClassification from is_investment + is_long_term, which can be read 
  from get_account_detail or passed in separately).

Read the layer READMEs before writing code:
- src/personal_finance/service/README.md (if it exists)
- src/personal_finance/domain/balance_sheet/account.py (to understand the domain model)

Run `.venv/bin/pytest` to confirm no regressions.

--

Why is our core service introducing an `AccountDetail` data class? Isn't that an application- (UI) layer concern?

---

/work-on-slice @specs/work-product/slice-logs/2026-06-13-workspace-cleanups.md

This is a Phase 2 (Implementation) session. Task 1 (service layer — update_account_metadata 
and get_account_detail) must already be complete before starting this.

## What to change

Read specs/canonical/03-user-interface/balance-sheet.md (flows F-4 and F-5) before starting.
Read src/personal_finance/ui/README.md.

### balance_sheet.py — AccountRow widget
- Remove the `TextInput` for the account name entirely; replace it with a `Static` label 
  (dim text, non-focusable, left-aligned, same width as the old input).
- Remove the `NameSubmitted` inner Message class.
- Remove `on_input_submitted` handling for the name field.

### balance_sheet.py — BalanceSheetScreen
- Add `Binding("f7", "edit_account", "Edit Account", show=True)` to BINDINGS.
- In `check_action`, add a branch: `if action == "edit_account"` → return True when any 
  account balance field (any MoneyInput or GoldBorderDisplay whose id starts with "bal-") 
  is focused. F7 is a contextual binding (right-aligned in the SplitFooter); add 
  "edit_account" to the contextual set passed to SplitFooter.
- Remove `on_account_row_name_submitted` and `_do_update_name`.
- Add `action_edit_account`: get the focused widget, derive account_id from its id 
  ("bal-{id}"), call `app.services.balance_sheet.get_account_detail(account_id)`, then 
  push AccountCreationDialog in edit mode (see below).
- In `_load_data`, change the initial focus from `.acct-name` (which no longer exists) to 
  the first `.acct-balance` input.

### balance_sheet_dialogs.py — AccountCreationDialog
Extend to support edit mode. Design: add an optional `existing: AccountDetail | None = None` 
parameter. When `existing` is not None:
- Title is "Edit Asset" / "Edit Liability" instead of "Create New …"
- All fields pre-populated from `existing`.
- The Nature row (id="nature-row") is replaced by a Static read-only label ("Simple" or 
  "Investment") — the RadioSet is not rendered.
- Classification and registration rows show/hide based on the existing nature 
  (not from the radio toggle, since the radio is gone).
- The Create button becomes Save; the save path calls 
  `app.services.balance_sheet.update_account_metadata(...)` and dismisses with the 
  account_id (same int return type so the caller can remain unchanged).

Import AccountDetail in balance_sheet_dialogs.py from the app service.

Run `.venv/bin/pytest` and then `.venv/bin/personal-finance` to verify the balance sheet 
screen still works, accounts display as labels, and F7 opens a pre-populated edit dialog.

---

/work-on-slice @specs/work-product/slice-logs/2026-06-13-workspace-cleanups.md 

Could you run all the tests, evaluate coverage, and identify areas that can be improved. 

--

All of the recommended tests, please.

--

While we're cleaning things up, could you please address these two bugs:

- "Amount left to invest" on the dashboard needs to refresh when you return to it.
- After entering a new holding in the Investment Editor, focus returns back to the top of the screen. Please keep the focus where it was before the edits took place.

--

Time to close up the current slice. U-3 appears to have already been dealt with (correct me if I'm wrong). Let me know if there's anything else missing.

I wanted to confirm the intention behind: 

> **U-2** — Does the Enter/Up/Down navigation refactor belong in `ModalDialogMixin`, a new mixin, or directly in the reusable input widgets themselves?

I believe the Enter/Up/Down is now handled within the inputs themselves, does the dialog mixin still play a role? 

--

Should we move Up/Down handling to the components themselves, or is there good reason for why they need to be in the screens and the `ModalDialogMixin`?

--

Perfect, then! Let's close out this slice. Let me know if there's anything outstanding.