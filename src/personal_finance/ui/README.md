# ui

The UI layer contains all Textual TUI code: the application, screens, and widgets. It communicates exclusively with the service layer and must never access the domain or database directly.

## Key Constraints

- The Textual event loop must never be blocked for more than 100 ms. Offload long-running work to background tasks.
- All user input must be validated before being passed to the service layer.

## Canonical Input Widgets

All interactive input and selection widgets must come from `ui/widgets/inputs.py` or `ui/widgets/date_input.py`. **Never use Textual's raw `Input`, `Select`, `Checkbox`, or `RadioSet` directly in screens or dialogs** — the canonical wrappers below enforce the application-wide keyboard convention (Enter advances focus, Space/arrows interact) and carry other app-specific behaviour.

### Governance rule

Before implementing a new input type or adding a new behaviour to an existing field:

1. **Stop and ask**: does an existing canonical widget cover this with a CSS tweak or constructor argument?
2. If not: should the existing widget be extended (add a parameter or subclass), or is this genuinely a new kind of field?
3. Only create a new widget class when the answer to (2) is "new kind of field". Document it here and in the widget module.

This prevents one-off field implementations from spreading behaviour inconsistencies across screens.

### Catalogue

| Widget | Source | Use for |
|---|---|---|
| `TextInput` | `inputs.py` | Free-text fields (names, labels). Left-aligned. Enter→next, Up/Down→navigate. |
| `MoneyInput` | `inputs.py` | Monetary amounts displayed as `$ X,XXX.XX`. Dollar sign pinned left, digits right-aligned. |
| `PercentInput` | `inputs.py` | Whole-number percentage entry displayed as `N.N%`. |
| `QuantityInput` | `inputs.py` | Share counts; integers without decimals, fractions to 4 d.p. |
| `DateInput` | `date_input.py` | YYYY-MM-DD masked entry. Enter→next, Esc reverts, blur commits or reverts. |
| `AppSelect` | `inputs.py` | Drop-down selects. Enter (closed) → next; Space/Down → open. Overflow flips to align with select's right edge. |
| `AppCheckbox` | `inputs.py` | Boolean toggles. Enter→next, Space→toggle. Strip the dark panel background in each dialog's CSS using the `AccountCreationDialog Checkbox` pattern in `balance_sheet_dialogs.py`. |
| `AppRadioSet` | `inputs.py` | Mutually-exclusive option groups. Enter→next; arrows and Space navigate/select within the group. |
| `GoldBorderDisplay` | `inputs.py` | Gold-bordered focusable read-only cell. Dollar sign left, value right. Size via CSS class on the instance. |
| `F6OpenableField` | `inputs.py` | Field that toggles between `MoneyInput` and `GoldBorderDisplay`. The owning widget handles `Input.Submitted`. |

`RightAlignedNumericInput` is the shared base for `MoneyInput`, `PercentInput`, and `QuantityInput`; import the concrete subclass, not the base.

## Color Palette

All screen/widget colors that represent a semantic role (panel fill, structural borders/dividers, dim/hint
text tiers, the tertiary accent) must come from `personal_finance.ui.palette` — import the named constant and
interpolate it into the `DEFAULT_CSS` f-string (or a Rich `style=` string), rather than hard-coding a new hex
literal. `netware.tcss` cannot import these (it's a static file loaded via `CSS_PATH`); its handful of
structural-color rules carry the same literal values by hand, each commented with the constant name they must
stay in sync with. See `palette.py`'s module docstring and
`specs/working-artefacts/adr/2026-08-05-frontend-visual-polish.md` for the contrast rationale behind each value.
Colors with no semantic role of their own (plain white text/borders, the `#0055cc` focus fill, gold borders,
warning red) stay as literals — only add a new palette token when a value is genuinely reused across screens
for the same purpose.

## Grid / Table Conventions

- **Column headers are always left-aligned**, regardless of whether the column contains numeric or monetary data. Right-aligning a header to match right-aligned cell values is visually inconsistent with the rest of the application and must not be done. Only cell *values* carry alignment (right for numbers, left for names/text).
- **`GoldBorderDisplay`** is the single canonical widget for gold-bordered focusable read-only cells. Do not create screen-specific equivalents. Size it via CSS classes on the instance, not in its own `DEFAULT_CSS`.
- **`F6OpenableField`** is the canonical widget for fields that toggle between an editable `Input` and a gold-bordered read-only cell. The owning row widget handles `Input.Submitted` directly — `F6OpenableField` does not intercept it.

## Modal Dialog Conventions

Every form-style dialog (`ModalScreen` subclass with input fields) must follow these conventions:

1. **Inherit `ModalDialogMixin`** (from `ui/screens/dialogs.py`) — provides up/down arrow key navigation across fields and the `F10` affirmative-action shortcut (presses the first enabled `variant="primary"` button).
2. **`on_mount` must call `.focus()` on the first interactive element.** Textual never auto-focuses inside a modal; without an explicit call the focus lands on an invisible container and Tab is required before any keyboard interaction works.
3. **Content goes in a `VerticalScroll`; buttons go outside it** — so buttons remain fixed at the bottom when content overflows.
4. **Use the global CSS classes** `dialog--title` (centered bold header), `dialog--buttons` (right-aligned button row), and `.dialog` (border/background/padding) defined in `netware.tcss`. Per-dialog size overrides belong in `netware.tcss`, not in `DEFAULT_CSS`.

## Two-Pane Screen Conventions

All screens built on `TwoPaneScreen` (or the same 33/67 left-nav / right-content pattern) must follow these focus rules:

- **Focus starts in the left pane.** After a screen mounts and its async worker loads data, do **not** auto-focus a widget in the right pane. Focus stays on the left nav pane until the user deliberately moves it with `Tab`, `Enter`, or a mouse click.
- **Exception — returning from a dialog.** When a create/edit dialog closes with a result, focus the relevant row in the right pane so the user is positioned on the item they just saved or returned to.
- **Refresh bindings on focus change.** Contextual bindings (F7, F8, …) are gated by `check_action` and shown/hidden by `SplitFooter`. The footer only updates when `refresh_bindings()` is called. Add `on_descendant_focus` and `on_descendant_blur` handlers that call `self.refresh_bindings()` so the footer reflects the correct set of available actions as the user tabs between panes.

## Known Textual Gotchas

Hard-won discoveries from development; check here before debugging Textual behaviour.

### 1. `_on_*` private handlers run for every class in the MRO

`_get_dispatch_methods` iterates `self.__class__.__mro__` and yields each class that has the method in its own `__dict__`. Overriding `_on_key` in a subclass does **not** prevent the parent's `_on_key` from being called. The only way to stop further iteration is `event.prevent_default()`. To intercept at the widget level without a parent side-effect, prefer `validate_value` or reactive override patterns rather than `_on_key` overrides.

### 2. `MaskedInput.validate_value` raises `ValueError` for non-matching characters (Textual bug)

`Input._on_key` calls `replace(char, start, end)` for printable keys. `replace` calls `check_allowed_value`, then sets `self.value`, which triggers `MaskedInput.validate_value` and raises `ValueError`. Fix in any `MaskedInput` subclass:

```python
def validate_value(self, value: str) -> str:
    try:
        return super().validate_value(value)
    except ValueError:
        return self.value  # self.value is still the old value here
```

### 3. `push_screen_wait` requires a worker context

`push_screen(screen, wait_for_dismiss=True)` raises `NoActiveWorker` when called from an action handler (which runs in the event-dispatch loop, not a worker). Use `push_screen` with a callback instead:

```python
def action_something(self) -> None:
    def _on_dismiss(result: bool | None) -> None:
        if result:
            ...
    self.app.push_screen(SomeDialog(...), callback=_on_dismiss)
```

### 4. `MaskedInput` subclass inner message must NOT be named `Changed`

Textual's `Input._watch_value` calls `self.Changed(self, value, validation_result)`, dynamically resolving to the most-derived `Changed` class. A subclass `Changed` receives the wrong constructor arguments and crashes. Name it something else (e.g. `DateChanged`).

### 5. Textual never auto-focuses inside a modal

When a `ModalScreen` opens, focus lands on the modal's root container — not on the first interactive widget. Every form-style dialog's `on_mount` must explicitly call `.focus()` on the first input. Reusable form widgets (e.g. `AssetAllocationForm`) should expose a `focus_first_input()` helper so host dialogs can satisfy this without knowing internal IDs.

### 6. Rich silently eats single-letter lowercase tag names inside `Static`

`Static` renders content through Rich markup by default. Rich treats `[x]`, `[v]`, `[o]`, and other single-letter lowercase strings as markup tags. Unknown tags are **silently dropped**, producing an empty string. `[ ]`, `[-]`, `[X]` (uppercase), and `[*]` survive because space, dash, uppercase, and `*` are not valid Rich tag-name characters.

**Fix:** Pass `rich.text.Text(indicator)` (a plain-text `Text` object) instead of a bare string, or set `markup=False` on the `Static` constructor. The same applies to `Static.update()` calls — pass `RichText(value)` there too.

```python
from rich.text import Text as RichText
yield Static(RichText("[ ]"), classes="checkbox")
# and in toggle():
static_widget.update(RichText("[x]"))
```

### 7. `ListItem` highlight class is `.-highlight`, not `.--highlight`

Textual's `ListItem.watch_highlighted` calls `self.set_class(value, "-highlight")` — **single dash**. The double-dash form (`.--highlight`) is never set and CSS rules targeting it are silently ignored. Use `.-highlight` in TCSS:

```css
SelectAccountsDialog ListItem.-highlight {
    background: #0055cc;
}
```

When overriding highlight colours for child widgets, add explicit rules in app-level TCSS (higher priority than DEFAULT_CSS) so Textual's `$block-cursor-foreground` inheritance does not bleed through:

```css
SelectAccountsDialog ListItem.-highlight .ali-checkbox { color: #ffffff; }
```

### 8. `check_action` must return `True`, not `None`, for enabled actions

`App.run_action` guards dispatch with `if action_target.check_action(action_name, params):` — a **truthiness** check. Returning `None` (Python's implicit return) evaluates as falsy and silently prevents the action from firing, even though the binding appears in the footer.

`Screen.active_bindings` uses `is False` to detect disabled actions, so `None` also produces `enabled=False` there, causing the footer key to render as greyed-out.

**Always return `True` as the fallthrough case in `check_action`:**

```python
def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
    if action == "contextual_only":
        return some_condition
    return True  # NOT None — None silently disables every other binding
```

### 9. `content-align` breaks `GoldBorderDisplay`/`MoneyInput`'s custom `$`-alignment for dollar values

`GoldBorderDisplay.render_line` and `MoneyInput.render_line` special-case values starting with `"$ "`: they call
`super().render_line(y)` to get the base widget's rendering, then crop/recompose it assuming the `"$ "` sits at
columns 0–1 (i.e. the base render is left-aligned). Setting `content-align: center` (or `right`) on either widget
shifts the base rendering *before* the crop happens, so the crop grabs blank padding instead of the `$` and the
value renders truncated/garbled. Only non-monetary content (e.g. a placeholder string) is safe to center/right-align
— dollar-formatted values are not, no matter what `content-align` says, because the crop logic ignores it and
hard-codes a left-aligned assumption. If a cell needs both monetary values (most rows) and a centered placeholder
(a specific row/state), scope the alignment override to a class added only in the placeholder case, not to the
widget or column generally — see `GoalRow.gr-goal-empty` in `screens/goals.py`.

### 10. Textual `$variable` substitution does not propagate across CSS sources

Each `Stylesheet` holds one `_variables` dict, populated once from `App.get_css_variables()` (Python/theme
values — this is how built-in tokens like `$footer-foreground` work everywhere). A `$name: value;` declared
inside a `.tcss` file's own root scope is *not* added back to that shared dict — it is only resolved within
tokens of that same parse pass. Concretely: a variable defined in `netware.tcss` is invisible to a screen's own
`DEFAULT_CSS` string (a separate source), and vice versa. This is why shared, semantic colors live in
`personal_finance.ui.palette` as plain Python constants interpolated into `DEFAULT_CSS` f-strings, not as
Textual `$variables` — see "Color Palette" above.
