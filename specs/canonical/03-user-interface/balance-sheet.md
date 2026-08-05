## Balance Sheet Flows

### Flow F‑4: View Balance Sheet Summary
**Goal:** See aggregated assets, liabilities, and net worth.

**Screen:** `BalanceSheetSummary`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Balance Sheet                                               2026-05-12 │
 ├────────────────────────────────────────────────────────────────────────┤
 │ Current Assets                                                         │
 │  Bank Account A                              [$   1,000.00]            │
 │  Bank Account B                              [$   2,234.22]            │
 │  Cashable GIC                                [$  10,000.00]            │
 │                                                                        │
 │ Current Assets Total                           $   13,234.22           │
 │                                                                        │
 │ Long-Term Assets                                                       │
 │  Home                                        [$ 500,000.00]            │
 │  Dad's TFSA                                  [$ 100,000.00]            │
 │  Mom's RRSP                                  [$ 100,000.00]            │
 │                                                                        │
 │ Long-Term Assets Total                         $  700,000.00           │
 │                                                                        │
 │ Current Liabilities                                                    │
 │  Visa                                        [$     852.42]            │
 │  MasterCard                                  [$   1,242.96]            │
 │                                                                        │
 │ Current Liabilities Total                      $    2,095.38           │
 │                                                                        │
 │ Long-Term Liabilities                                                  │
 │  Mortgage                                    [$  52,439.45]            │
 │                                                                        │
 │ Long-Term Liabilities Total                    $   52,439.45           │
 │                                                                        │
 │ Current Net Worth:     $   11,138.84   Total Net Worth: $  658,699.39  │
 ├────────────────────────────────────────────────────────────────────────┤
 │ [Esc] Back  [F2] New Asset  [F3] New Liability  [F5] Refresh  [F6] Open  [F7] Edit Account  [F8] Discard │
 └────────────────────────────────────────────────────────────────────────┘
```

- **Panel Descriptions:**
  - Split into four full-width row sections: Current Assets, Long-Term Assets, Current Liabilities, and Long-Term Liabilities.
  - Each section calculates its own total based on values matching the effective date context.
  - Current Net Worth (Current Assets - Current Liabilities) and Total Net Worth (Total Assets - Total Liabilities) are calculated at the bottom.
  - Account names are **static labels** — they are not directly editable in-place. To rename an account or change its metadata, use `F7`.
  - Simple accounts display an editable numeric balance input.
  - Investment accounts display a gold-bordered read-only balance (focusable but not editable). Pressing `F6` when this field is focused navigates to the Investment Editor (Flow F-6). `F7` is also available when this field is focused to edit the account metadata.
  - `F7` is a **contextual** footer binding: it appears (right-aligned) only when focus is on an account row's balance field.

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate focus between account balance fields.
- `Enter` on a modified balance field → Persist the new value.
- `F6` (when a gold-bordered investment balance has focus) → Navigate to the Investment Editor (Flow F-6).
- `F7` (when any account balance field has focus) → Open `AccountCreationDialog` in edit mode (Flow F-5).
- `F2` → Open `AccountCreationDialog` defaulting to an Asset.
- `F3` → Open `AccountCreationDialog` defaulting to a Liability.
- `F5` → Reload all account data and recalculate totals.
- `F8` → Trigger `ConfirmationDialog` to discard the currently focused account.
- `Esc` (when not editing) → Navigate back to `Dashboard`.

**Transition:**
- To `ConfirmationDialog` (Flow F-25) upon pressing `F8`.
- To `AccountCreationDialog` (Flow F-5) upon pressing `F2`, `F3`, or `F7`.
- To `InvestmentEditorScreen` (Flow F-6) upon pressing `F6`.
- To `Dashboard` upon `Esc`.

**Reference:**
- `BS-1` (View Balance Sheet)
- `BS-2` (Manage Accounts)
- `BS-4` (Revalue Holdings)
- `BS-OP-1`, `BS-OP-2`, `BS-OP-3`, `BS-OP-4`

### Flow F‑5: Create / Edit Account Dialog
**Goal:** Create a new account, or edit the metadata of an existing one.

**Screen:** `AccountCreationDialog` (modal)
- **Applicable Screens:** `BalanceSheetSummary`
- **Layout (create mode):**
```text
 ┌────────────────────────────────────────────────────────┐
 │ Create New Asset                                       │
 ├────────────────────────────────────────────────────────┤
 │ Account Name:        [ Tangerine Checking         ]    │
 │ Term Classification: ( ) Current   (•) Long-Term       │
 │ Nature:              (•) Simple    ( ) Investment       │
 │ Classification:      [ Bank                     ▼ ]    │
 │ Owner(s):            [x] Mom                           │
 │                      [x] Dad                           │
 │                                                        │
 │                                    [Cancel] [Create]   │
 └────────────────────────────────────────────────────────┘
```
- **Layout (edit mode):**
```text
 ┌────────────────────────────────────────────────────────┐
 │ Edit Asset                                             │
 ├────────────────────────────────────────────────────────┤
 │ Account Name:        [ Tangerine Checking         ]    │
 │ Term Classification: ( ) Current   (•) Long-Term       │
 │ Nature:                Simple                          │
 │ Classification:      [ Bank                     ▼ ]    │
 │ Owner(s):            [x] Mom                           │
 │                      [x] Dad                           │
 │                                                        │
 │                                    [Cancel] [  Save ]  │
 └────────────────────────────────────────────────────────┘
```
- **Field descriptions:**
  - Input: *Account Name* — editable in both modes.
  - Radio pair: *Term Classification* (Current vs Long-Term) — editable in both modes.
  - Radio pair: *Nature* (Simple vs Investment, Assets only) — editable in **create mode** only. In edit mode it is shown as a read-only label; converting between Simple and Investment after creation is not supported.
  - Select (Liabilities and Simple accounts only): *Classification* (e.g., Bank, Receivable/Payable, Real Estate, etc.) — editable in both modes.
  - Select (Investment accounts only): *Registration* (e.g., TFSA, RRSP, RESP, etc.) — editable in both modes.
  - Checkboxes: *Owner(s)* — one checkbox per `Person` in the household; editable in both modes. At least one owner must be selected.
- **Titles and buttons:**
  - Create mode: title "Create New [Asset | Liability]", buttons `[Cancel]` `[Create]`.
  - Edit mode: title "Edit [Asset | Liability]", buttons `[Cancel]` `[Save]`.

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields.
- `Enter` on `[Create]` → Save the new account and return to Balance Sheet Summary, focusing the new row.
- `Enter` on `[Save]` → Persist changes to the account and return to Balance Sheet Summary, restoring focus to the row that triggered the dialog.
- `Esc` or `Enter` on `[Cancel]` → Close dialog without saving.

**Reference:**
- `BS-2` (Manage Accounts)
- `BS-OP-5`

### Flow F‑6: View & Edit Investment Holdings
**Goal:** View and manage cash balance and holdings (holdings) of an investment account.

**Screen:** `InvestmentEditorScreen`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Dad's TFSA                                                  2026-05-12 │
 ├────────────────────────────────────────────────────────────────────────┤
 │ Uninvested Cash Balance                        [$             1,200.00]│
 │                                                                        │
 │ Holdings                                                           │
 │ Name                   Symbol   Quantity       Total        Allocation │
 │  Microsoft Corporation   MSFT  [       10]  $   2,400.00       [100%]  │
 │ [GIC                  ]   -       -        [$  10,000.00]      [  0%]  │
 ├────────────────────────────────────────────────────────────────────────┤
 │ Total                                               $   13,600.00      │
 ├────────────────────────────────────────────────────────────────────────┤
 │ [Esc] Back  [F2] Add Holding              [F6] Edit Allocation  [F8] Discard Holding │
 └────────────────────────────────────────────────────────────────────────┘
```

- **Panel Descriptions:**
  - Title shows the name of the Investment account (read-only; editing is already covered in the `BalanceSheetSummary`).
  - Top row allows editing the temporal cash value (`cashBalance`).
  - Below is the holdings table for both exact (manual) and listed security types.
  - The type of a holding cannot be changed once created.
  - For Listed Security rows: *Name* and *Symbol* are disabled (from API); *Quantity* is editable; *Total* is disabled (calculated).
  - For exact/manual rows: *Name* is editable; *Symbol* and *Quantity* are not applicable and disabled; *Total* is editable.
  - *Allocation* column shows a gold-bordered read-only input for every row displaying the total allocated percentage. Pressing `F6` when this field is focused opens the `HoldingAllocationDialog` (Flow F-7b).
  - A read-only **Total bar** is fixed below the scroll area, showing the sum of the uninvested cash balance and all active holding values. It updates in-place after each successful edit (cash balance, exact amount, or listed quantity when a unit price is available).

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields within the grid and cash balance.
- `Enter` on a modified field → Persist changes mapping to the current session effective date.
- `F6` (when a gold-bordered allocation cell has focus) → Open `HoldingAllocationDialog` (Flow F-7b).
- `F2` → Open `AddHoldingDialog` (Flow F-7a).
- `F8` → Trigger `ConfirmationDialog` to discard the focused holding (no-op if focused on cash balance).
- `Esc` (when not editing) → Go back to `BalanceSheetSummary`.

**Transition:**
- To `AddHoldingDialog` upon pressing `F2`.
- To `HoldingAllocationDialog` upon pressing `F6`.
- To `ConfirmationDialog` upon pressing `F8`.
- To `BalanceSheetSummary` upon `Esc`.

**Reference:**
- `BS-3` (Manage Investment Holdings)
- `BS-4` (Revalue Holdings)

### Flow F‑7a: Add Holding Dialog
**Goal:** Add a new listed security or manual entry holding, including initial allocation.

**Screen:** `AddHoldingDialog` (modal)
- **Applicable Screens:** `InvestmentEditorScreen`
- **Layout:**
  - Starts by prompting for the holding type via radio buttons.
  - Listed Security path: symbol text search field; pressing Enter triggers BS-OP-13 and displays up to five results as radio buttons below the field. No result is auto-selected; focus moves to the first radio button after a successful search (stays on the search field if no results — an error dialog appears instead). Selecting a result triggers an async price fetch that populates Unit Price and Total. Total updates live as Quantity changes.
  - Manual Entry path: Name and Total text inputs.
  - The `[Create]` button is disabled until the allocation percentages sum to 100%.

```text
 ┌────────────────────────────────────────────────────────┐
 │ Add Holding                                        │
 ├────────────────────────────────────────────────────────┤
 │ Type:  (•) Listed Security    ( ) Manual Entry         │
 │                                                        │
 │ Symbol:      [ MSFT                  ]                 │
 │              ( ) MSFT — Microsoft Corporation (NASDAQ) │
 │              ( ) MSFT.L — Microsoft Corp (LSE)         │
 │ Quantity:    [       10 ]                              │
 │ Name:        Microsoft Corporation                     │
 │ Unit Price:  $ 240.00                                  │
 │ Total:       $ 2,400.00                                │
 │                                                        │
 │ Asset Allocation                                       │
 │ US Equity            [ 100 ] %                         │
 │ Fixed Income         [   0 ] %                         │
 │ Canadian Equity      [   0 ] %                         │
 │ Total:                 100 %                           │
 │                                                        │
 │                                    [Cancel] [Create]   │
 └────────────────────────────────────────────────────────┘
```

- **Panel Descriptions:**
  - If **Listed Security** is selected: shows `Symbol` text input; pressing `Enter` runs a BS-OP-13 symbol search. Up to five results appear as individually-selectable radio buttons (in the same vertical list style as ownership checkboxes in F-5). No result is auto-selected; focus moves to the first radio button after results appear. Redoing the search clears the previous selection. Selecting a result shows `Name` (from search data), fetches `Unit Price` asynchronously (displays "Loading…" while in flight), and computes `Total = Unit Price × Quantity` once pricing completes. `Quantity` is an editable input; changing it recalculates `Total` live whenever a unit price is available.
  - If **Manual Entry** is selected: hides the listed fields and instead shows `Name` and `Total` as regular inputs.
  - Below the type-specific inputs, displays a list of all active `AccountAssetClass`es with numeric percentage inputs (the `AssetAllocationForm` widget, also used in F-7b). A running total is shown; `[Create]` is enabled only when it equals 100%.

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields.
- `Enter` on the Symbol field → Trigger symbol search (BS-OP-13). Shows results or an error dialog if no results are found.
- `Space` on a search result radio button → Select that security (triggers price fetch).
- `Enter` on `[Create]` → Save the new holding with its allocations. Closes dialog and triggers a reload of the Investment Editor.
- `Esc` or `Enter` on `[Cancel]` → Close without saving.

**Reference:**
- `BS-3` (Manage Investment Holdings)
- `BS-5` (Search for Securities)

### Flow F‑7b: Edit Asset Allocation Dialog
**Goal:** Adjust the asset allocation for an existing holding.

**Screen:** `HoldingAllocationDialog` (modal)
- **Applicable Screens:** `InvestmentEditorScreen`
- **Layout:**
```text
 ┌────────────────────────────────────────────────────────┐
 │ Asset Allocation                                       │
 ├────────────────────────────────────────────────────────┤
 │ [US Equity         ] [ 100 ] %                         │
 │ [Fixed Income      ] [   0 ] %                         │
 │ [Canadian Equity   ] [   0 ] %                         │
 │ Total:                 100 %                           │
 │                                                        │
 │                                    [Cancel] [ Save ]   │
 └────────────────────────────────────────────────────────┘
```
- **Panel Descriptions:**
  - A list of all active `AccountAssetClass`es with inputs. Sum must equal 100%.

**Actions:**
- `Tab` / `Shift+Tab` / `Up` / `Down` → Navigate fields.
- `Enter` on `[ Save ]` → Save changes to the allocations. Closes dialog.
- `Esc` or `Enter` on `[Cancel]` → Close without saving.

**Reference:**
- `BS-3` (Manage Investment Holdings)

