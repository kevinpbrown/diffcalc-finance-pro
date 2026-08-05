# User Interface Flows (Layer 3)

This document defines concrete interaction patterns and screen‑by‑screen flows for each functional requirement. It describes how the user navigates through the Textual UI to accomplish tasks, linking each flow to the required operations from Layer 2. This file specifies all our TUI principles and describes all shared components. You will find module-specific UI flows in the following files:

- Balance Sheet: `./balance-sheet.md`
- Cash Flow: `./cash-flow.md`
- Goals: `./goals.md`

## TUI Principles

### 1. Look and Feel

**Color Palette (Netware-style):**

Role-based tokens (everything below except the one-off accent/status colors) are centralized in
`personal_finance/ui/palette.py` as plain Python constants, interpolated into each screen's `DEFAULT_CSS`
f-string — see that module's docstring for why (Textual's `$variable` CSS substitution does not propagate
across separate CSS sources, so a shared `netware.tcss` value can't be referenced from a screen's own
`DEFAULT_CSS`). `netware.tcss` itself carries the small number of *structural* rules (input/select borders,
scrollbars, panel/dialog/button fills) as literal hex kept in sync by hand, each commented with the constant
name it mirrors. See `specs/working-artefacts/adr/2026-08-05-frontend-visual-polish.md` for the WCAG contrast
rationale behind the values below.

| Role | Value | Notes |
|------|-------|-------|
| Screen background | `#000080` (dark navy) | The "desktop" behind all panels |
| Panel / dialog / title-bar / button background | `#1a1ab0` (`PANEL_FILL`) | One deliberately modest step brighter than the screen background, for depth — white borders remain the primary layering cue, not this fill |
| Panel border | `#ffffff` (white) | `solid` borders on all containers |
| Normal text | `#ffffff` (white) | Default body text |
| Secondary text | `#aaaaaa` (silver) | Labels, column headers, secondary values |
| Dim text | `#9a9ad6` (`TEXT_DIM`) | Unselected nav items, dim account/category names, blocked list rows |
| Hint / placeholder text | `#7a7ab3` (`TEXT_HINT`) | Lowest tier of the text hierarchy (primary → secondary → dim → hint): splash skip-hint, manual-entry placeholders, empty-state text |
| Input / select (unfocused) background | `#000080` | Editable fields at rest |
| Input / select (unfocused) border | `#6666cc` (`BORDER_STRUCTURAL`) | Also used for load-bearing nav-pane split borders and panel-boundary rules — anything structural, not decorative |
| Input (focused) | `#0055cc` background, `#aaaaff` border | Editable fields with focus — clearly brighter |
| Input (invalid) | `#aa0000` background, `#ff5555` border | Validation failure state |
| Tertiary divider accent | `#00aaaa` (`ACCENT_CYAN`) | Decorative in-content `Rule` separators **only** (currently: Cash Flow module dividers) — never borders, buttons, or primary text |
| Accent / highlight | `#cc0000` (Netware red) | Focused buttons |
| Footer / header bar | `#1a1ab0` background, `#aaaaff` text | |
| Scrollbar | `#aaaaff` thumb (`#ffffff` while dragging) on `#000066` track | Explicitly set app-wide via a universal (`*`) selector |
| Warning text | `#ff4444` | `[!]` overclaim warnings, validation banners |
| Button default | `#1a1ab0` background, `#ffffff` text | |
| Button focused | `#cc0000` background, `#ffffff` text | Red highlight on active button |

- Editable fields get a solid background that gets brighter when focused.
- No gradients, no shadows — flat, block-color panels only.
- ASCII box-drawing characters (`┌─┐│└┘├┤`) for visible borders in mockups; Textual renders these with widget borders.

### 2. Navigation & Focus

- Both `Tab` and `Enter` navigate from one field to the next.
- Pressing `Enter` without making a change to a field is a no-op navigation.
- `Shift+Tab` moves focus backwards.
- `Up`/`Down` arrow keys navigate focusable items in list-style layouts (menu items, table rows).
- `Left`/`Right` arrow keys navigate between buttons in a horizontal button group (e.g., dialog button rows).
- With the exception of when editing a field, `Esc` will take the user back one level in the application. `Esc` on the landing screen (the Dashboard) will show a `ConfirmationDialog` asking whether to quit.
- When a dialog closes (confirmed or cancelled), input focus must return to the widget that triggered its opening. When the save path triggers a full data reload (destroying and recreating widgets), the screen is responsible for explicitly re-focusing the originating field by ID after the reload completes; it cannot rely on Textual's automatic focus restoration in this case.
- On a new screen opening, focus should be placed on the first interactive element unless a more natural default exists (e.g., the primary action button for a create dialog).

### 3. Data Entry & Editing

- Starting to change a numeric field clears the visible content; character-level editing is not supported. If the user presses `Esc` before navigating away, the field resets to its current committed value.
- Some fields have more detailed configuration via a companion `"..."` button that opens a dialog. E.g., `[$ 10,000.00 | ...]`. The numeric input and the companion button are separate focusable entities.
- Fields that are computed or lead to a sub-screen are rendered as **gold-bordered read-only inputs** — focusable but not editable. Pressing `F6` while such a field is focused opens the associated sub-screen or dialog. `>` drill-through buttons do **not** exist; the gold-bordered input is the sole affordance for drill-down.
- Fields that need to be validated together must always be grouped in a dialog. Scalar entries without dependencies should be placed directly on a panel wherever possible.
- **Date fields** are plain text inputs with format `YYYY-MM-DD` and immediate parse validation. Textual does not ship a calendar widget; the `DateInput` shared widget handles format enforcement and validation.
- **Dropdown selects** (`Select`) default to the first valid option unless editing an existing record, in which case they default to the current value.

### 4. Validation & Error Handling

- Invalid entries turn the input box light red (`#aa0000` / `invalid` CSS class) and prevent focus from leaving the field. `Esc` exits the invalid state by reverting to the last committed value.
- Field-level validation is immediate (on change). Cross-field validation is deferred to form submission / dialog save.
- Service-layer errors (e.g., a failed quote fetch) are surfaced via the `ErrorDialog` (Flow F-24). The screen should remain usable after dismissal when possible.
- The UI must never expose raw exception tracebacks; human-readable messages only. Technical details go to structured logs.

### 5. Global Operations & Keybindings

- Function keys (`F2`, `F3`, `F4`, `F6`, `F8`), `Insert` drive create/navigate/discard operations on full-screen panels. A `Footer` widget displaying all active bindings is shown at the bottom of every screen.
- `F6` is the universal drill-down key for gold-bordered read-only inputs on full-screen panels. It opens the sub-screen or dialog associated with the focused field and is a no-op when focus is not on a gold-bordered input.
- `F8` is the universal "discard selected entry" key on full-screen panels. `Delete` is **not** used for discard — it functions as a standard character-clearing key inside editable inputs.
- These keys are scoped to full-screen panels. Modal dialogs must not capture them unless the flow explicitly requires it.
- `F10` is the universal **modal affirmative action** key. When pressed inside any `ModalDialogMixin` dialog, it activates the first enabled `variant="primary"` button (equivalent to clicking `[Create]` / `[Save]`). It is a no-op when no such button exists or the button is disabled. `F10` must not be bound on full-screen panels.
- `Q` as a quick-quit shortcut is available only on the Dashboard.
- The Footer is hidden when a dialog is open.

### 6. Global Context

- The "Session Effective Date" is set exclusively on the Dashboard. All module screens that consume temporal data display it as read-only text in the top-right of their header row (e.g., `Balance Sheet                    2026-05-12`).
- The effective date drives all value lookups (`EffectiveAmount.latest_value_as_of`, pricing calls, active-state filters). Changing it on the Dashboard triggers a reactive refresh of `Amount Left to Invest`.

### 7. Screen Layout Chrome

Every full-screen panel follows this layout pattern:

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ <Module Title>                                          <Effective Date> │
 ├──────────────────────────────────────────────────────────────────────────┤
 │                                                                          │
 │  <Body content>                                                          │
 │                                                                          │
 ├──────────────────────────────────────────────────────────────────────────┤
 │ [F2] …  [F3] …  [Esc] Back                [F6] Open  [F8] Discard        │
 └──────────────────────────────────────────────────────────────────────────┘
```

- **Title bar:** module name left-aligned, effective date right-aligned (omitted for the Dashboard itself which is the date setter, and for screens without temporal context).
- **Body:** scrollable when content overflows.
- **Footer:** A split `SplitFooter` widget populated from the screen's `BINDINGS`. Constant bindings (navigation, creation — always available) are left-aligned. Contextual bindings (row-level operations that depend on the focused item — e.g., `F6 Open`, `F8 Discard`) are right-aligned. This visual separation guides the eye: glance left for navigation, glance right for what you can do with the selected item.
- Each screen declares which of its actions are contextual by passing the set of action names to `SplitFooter`.

Dialogs omit the title bar and footer. They have their own title in the dialog chrome and always end with `[Cancel] [Action]` buttons (Cancel left, action right).

### 8. Asynchronous Work & Loading States

- The Textual event loop must never be blocked for more than 100 ms (per the Technical Charter). All service calls that do I/O (price fetches, DB queries on large datasets) must run in background workers via `self.run_worker(...)`.
- While a background worker is running, the relevant portion of the screen must show a loading indicator (a `LoadingIndicator` widget or a `"Loading…"` static label, depending on the scope).
- If a worker fails, post a `Notify` toast for transient warnings or push the `ErrorDialog` screen for blocking failures.
- Read-only computed values (like `Amount Left to Invest`) that depend on async data should display `"—"` or `"Calculating…"` until the worker completes.

### 9. Data Formatting

- **Numeric alignment (mandatory):** All numeric values — whether displayed as read-only text, in editable input fields, or in table columns — **must be right-aligned** unless a flow explicitly states otherwise. This applies to currency, percentages, counts, and any other numeric type.
- **Currency:** Always display with two decimal places, right-aligned, prefixed with `$` and a non-breaking space. Thousands-separated. Negative values prefixed with `−` (minus sign). Example: `$  12,500.00`, `−$    345.00`.
- **Dates:** Always `YYYY-MM-DD` in both input and display contexts.
- **Percentages:** One decimal place, right-aligned. Example: `17.3%`.
- **N/A values:** Display `—` (en-dash) rather than empty string or `None`.

### 10. Empty States

- When a list or table has no records, display a centred, dim-text message: e.g., `No accounts. Press F2 to add one.`
- Empty states must not be blank; always include a hint about how to add data.

### 11. Modal Patterns

- Dialogs are `ModalScreen` subclasses that compose their own layout. They overlay the parent screen without replacing it.
- Default button focus: `[Cancel]` on open for destructive dialogs; `[Action]` on open for create/edit dialogs.
- `Esc` in a dialog always cancels (equivalent to clicking `[Cancel]`), as long as no field is currently in an invalid state.
- `F10` activates the affirmative button (`[Create]` / `[Save]`) from anywhere in the dialog, provided the button is enabled. This is a shortcut for users who want to submit without tabbing through all fields first.
- After saving, the dialog dismisses and the parent screen refreshes its relevant data (via a message/event posted back to the parent). The screen must then restore focus to the field that opened the dialog (see §2 Navigation & Focus).

## Flow Notation

- **Screen:** or **Dialog:** A named UI screen (e.g., “Dashboard”, “Account List”) or dialog.
- **Applicable Screens**: For dialogs only, this makes it clear over which screens this will be reused.
- **Action:** User input (keystroke, button click, menu selection).
- **Transition:** Movement between screens or states.
- **Reference:** Links to Layer‑2 operations (e.g., `BS‑OP‑1`) and Layer‑1 functional requirements (e.g., `BS‑1`).

## Application Startup

### Flow F‑1: Launch
**Goal:** Start the application.

**Screen:** `SplashScreen`
- Shows the application wordmark (block-letter ANSI-art, styled per the Color Palette above: white
  glyphs with a `BORDER_STRUCTURAL`-colored drop shadow), version, and copyright.
- Initializes database components and seed data in a background worker, updating a status line as it
  progresses (e.g., "Connecting to database…", "Ready.").
- Held on screen for a minimum duration (`App._MIN_SPLASH_SECONDS`) even if initialization finishes
  sooner, so the splash doesn't flash by unreadably fast; a "Press Enter to skip" hint (hint-tier text)
  is shown below the status line, and pressing `Enter` at any time skips the remaining minimum hold.

**Actions:**
- `Enter` → skip the remaining minimum display time and proceed immediately once init is complete.

**Transition:**
- Automatically transitions to `Dashboard` once initialization completes and the minimum hold (or an
  `Enter` skip) has elapsed.

## Dashboard

### Flow F‑3: View Dashboard
**Goal:** Set the session effective date and navigate to main application modules.

**Screen:** `Dashboard`
- No title bar (the Dashboard is the effective-date setter itself, exempted per §7). Content is
  horizontally centered but anchored near the top of the screen (`align: center top` with a small top
  margin), not vertically centered — closer to how NetWare/Classroom LAN menu screens actually sat.
- **Layout, top to bottom:**
  1. "Session Effective Date" row (label + `DateInput`).
  2. A bordered stats panel: `Amount Left to Invest`, `Current Net Worth`, `Total Net Worth` (all
     right-aligned `$` values; `"Calculating…"` shown until the backing worker resolves — see §8).
  3. A bordered "Available Options" menu box: title, a separator rule, then the navigation `ListView`.

```text
                                              ┌────────────────┐
                   Session Effective Date:    │  2026-05-12    │
                                              └────────────────┘

                              ┌──────────────────────────────────────────────┐
                              │Amount Left to Invest:         $     12,500.00│
                              │Current Net Worth:             $     76,500.00│
                              │Total Net Worth:                $  1,499,171.49│
                              └──────────────────────────────────────────────┘

                           ┌────────────────────────────────────────────────────┐
                           │                 Available Options                  │
                           │────────────────────────────────────────────────────│
                           │ Balance Sheet                                      │
                           │ Goals                                              │
                           │ Cash Flow                                          │
                           │ Quit                                               │
                           └────────────────────────────────────────────────────┘
```

- **Menu Options:**
  - `Balance Sheet`
  - `Goals`
  - `Cash Flow`
  - `Quit`
- The menu's `ListView` highlight is hidden while focus is elsewhere on the screen (e.g. the date
  field); it shows a dark-navy (`#000080`) bar only when the list itself is focused.

**Actions:**
- `Up/Down` or `Tab` → Navigate menu items and date picker.
- `Enter` on `Session Effective Date` → Adjust the global temporal context (which actively recalculates Amount Left to Invest, Current Net Worth, and Total Net Worth).
- `Enter` on `Balance Sheet` → Proceed to the Balance Sheet module.
- `Enter` on `Goals` → Proceed to the Goals module.
- `Enter` on `Cash Flow` → Proceed to the Cash Flow module.
- `Enter` on `Quit`, `Esc`, or `Q` → Trigger application exit.
- `F5` → Refresh the stats panel.

**Transition:**
- To `BalanceSheetSummary` (Flow F-4)
- To `GoalsList` (Flow F-8)
- To `CashFlowProjection` (Flow F-12)
- Exit Application

**Reference:** 
- `GEN-1` (Set Effective Date Context)
- `GEN-OP-2` (`GeneralService.get_dashboard_summary`, via `DashboardService.get_summary`) — prices all
  securities once and computes all three stats panel values together. Not documented in the Layer-2 spec
  (`specs/canonical/02-operations/service-operations.md`).


## Module-Specific Flows

- [Balance Sheet Flows](balance-sheet.md)
- [Goals Flows](goals.md)
- [Cash Flow Flows](cash-flow.md)

## Error & Confirmation Flows

### Flow F‑24: Error Display
**Goal:** Show user‑friendly error messages.

**Screen:** `ErrorDialog` (modal)
- Icon: `[✗]` for errors, `[!]` for warnings.
- Message: Human‑readable text.
- Details: Expandable technical details (logged, not shown by default).
- Buttons: `[OK]` `[Copy to Clipboard]`.

**Actions:**
- `Enter` → dismiss.
- `Esc` → dismiss.

### Flow F‑25: Confirmation Dialog
**Goal:** Confirm discard actions.

**Screen:** `ConfirmationDialog` (modal)
- Question: “Discard account ‘Chequing Account’?”
- Buttons: `[Yes]` `[No]` (default No).

**Actions:**
- `Enter` or `Space` on `[Yes]` → confirm.
- `Enter` or `Space` on `[No]` → cancel.
- `Left`/`Right` → move focus between buttons.
- `Esc` → cancel.

## Flow Traceability

Each UI flow implements one or more functional requirements (Layer 1) and calls specific operations (Layer 2). The mapping is maintained in the slice logs during implementation.

**Example:**
- Flow F‑4 (View Balance Sheet Summary) → `BS‑2` (Manage Accounts) → `BS‑OP‑1`, `BS‑OP‑2`, `BS‑OP‑3`, `BS‑OP‑4`.
- Flow F‑5 (Create Account Dialog) → `BS‑2` (Manage Accounts) → `BS‑OP‑5`.
- Flow F‑12 (View Cash Flow Projection) → `CF‑3` (View Monthly Cash Flow Projection) → `CF‑OP‑3`.

Developers must update the slice log’s “UI Flows Implemented” checklist as each flow is completed.
