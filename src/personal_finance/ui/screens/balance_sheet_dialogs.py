"""Balance Sheet modal dialogs — Flows F-5, F-7a, and F-7b.

Implements:
- AccountCreationDialog          (Flow F-5)  — create a new Simple or Investment account
- AddHoldingDialog           (Flow F-7a) — add a listed or exact holding with allocation
- HoldingAllocationDialog    (Flow F-7b) — edit asset allocation for an existing holding
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import structlog
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RadioButton, Static

from personal_finance.core.interfaces import QuoteServiceError
from personal_finance.service.application.balance_sheet_app_service import (
    AccountAssetClassOption,
    AccountClassification,
    AccountDetail,
    InvestmentRegistration,
    PersonOption,
    SecuritySearchResult,
    SimpleAccountCategory,
)
from personal_finance.ui.palette import TEXT_DIM
from personal_finance.ui.screens.dialogs import ErrorDialog, ModalDialogMixin
from personal_finance.ui.widgets.allocation_form import AssetAllocationForm
from personal_finance.ui.widgets.inputs import (
    AppCheckbox,
    AppRadioSet,
    AppSelect,
    MoneyInput,
    QuantityInput,
    TextInput,
)

logger = structlog.get_logger(__name__)

# ── Option lists for Classification / Registration selects ────────────────────

_CLASSIFICATION_OPTIONS: list[tuple[str, SimpleAccountCategory]] = [
    ("Bank", SimpleAccountCategory.BANK),
    ("Receivable / Payable", SimpleAccountCategory.RECEIVABLE_PAYABLE),
    ("Real Estate", SimpleAccountCategory.REAL_ESTATE),
    ("Vehicle", SimpleAccountCategory.VEHICLE),
    ("Other", SimpleAccountCategory.OTHER),
]

_REGISTRATION_OPTIONS: list[tuple[str, InvestmentRegistration]] = [
    ("RRSP", InvestmentRegistration.RRSP),
    ("TFSA", InvestmentRegistration.TFSA),
    ("RESP", InvestmentRegistration.RESP),
    ("LIRA", InvestmentRegistration.LIRA),
    ("DPSP", InvestmentRegistration.DPSP),
    ("Unregistered", InvestmentRegistration.UNREGISTERED),
]


# ── AccountCreationDialog ─────────────────────────────────────────────────────


class AccountCreationDialog(ModalDialogMixin, ModalScreen[int | None]):
    """Modal dialog to create a new or edit an existing account — Flow F-5.

    Yields the account's database ID on success, or ``None`` on cancel.

    Args:
        side: ``"asset"`` when launched via F2/F7, ``"liability"`` when via F3/F7.
        persons: Selectable persons from the database.
        existing: When provided, opens in edit mode pre-populated with this data.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    AccountCreationDialog .acd-row {
        height: 3;
        layout: horizontal;
    }
    AccountCreationDialog .acd-owners-row {
        height: auto;
        layout: horizontal;
        margin-top: 1;
    }
    AccountCreationDialog .acd-label {
        width: 22;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    AccountCreationDialog .acd-owners-row .acd-label {
        height: auto;
        content-align: left top;
        padding-top: 1;
    }
    AccountCreationDialog .acd-field {
        width: 1fr;
        height: 3;
    }
    AccountCreationDialog .acd-nature-label {
        color: #ffffff;
        content-align: left middle;
    }
    AccountCreationDialog RadioSet {
        layout: horizontal;
        height: 3;
        border: none;
        background: transparent;
        padding: 0;
        width: 1fr;
        align: left middle;
    }
    AccountCreationDialog RadioSet:focus {
        border: none;
    }
    AccountCreationDialog RadioButton {
        background: transparent;
        height: 1;
        width: 1fr;
    }
    AccountCreationDialog RadioButton:focus {
        background: #0055cc;
    }
    AccountCreationDialog #owners-checks {
        layout: vertical;
        height: auto;
        background: transparent;
        width: 1fr;
    }
    AccountCreationDialog Checkbox {
        height: 1;
        width: 100%;
        border: none;
        background: transparent;
        padding: 0 1;
    }
    AccountCreationDialog Checkbox:focus {
        border: none;
        background: #0055cc;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        side: str,
        persons: list[PersonOption],
        existing: AccountDetail | None = None,
    ) -> None:
        """Store the side, persons list, and optional existing account data."""
        super().__init__()
        self._side = side
        self._persons = persons
        self._existing = existing

    def compose(self) -> ComposeResult:
        """Render all dialog fields appropriate for the chosen side and mode."""
        is_edit = self._existing is not None
        if is_edit:
            title = f"Edit {'Asset' if self._side == 'asset' else 'Liability'}"
        else:
            title = "Create New Asset" if self._side == "asset" else "Create New Liability"

        # Pre-compute initial term selection for both modes
        is_long_term_init = self._existing.is_long_term if self._existing else False

        with Vertical(classes="dialog"):
            yield Static(title, classes="dialog--title")

            # Account name
            with Horizontal(classes="acd-row"):
                yield Label("Account Name:", classes="acd-label")
                yield TextInput(
                    value=self._existing.name if self._existing else "",
                    id="acct-name",
                    classes="acd-field",
                )

            # Term classification — radio buttons (pre-selected in edit mode)
            with Horizontal(classes="acd-row"):
                yield Label("Term Classification:", classes="acd-label")
                yield AppRadioSet(
                    RadioButton("Current", value=not is_long_term_init),
                    RadioButton("Long-Term", value=is_long_term_init),
                    id="term-radio",
                )

            # Nature row — radio in create mode, static label in edit mode (assets only)
            if self._side == "asset":
                with Horizontal(classes="acd-row", id="nature-row"):
                    yield Label("Nature:", classes="acd-label")
                    if is_edit:
                        nature_label = "Investment" if self._existing.is_investment else "Simple"  # type: ignore[union-attr]
                        yield Static(nature_label, classes="acd-field acd-nature-label")
                    else:
                        yield AppRadioSet(
                            RadioButton("Simple", value=True),
                            RadioButton("Investment"),
                            id="nature-radio",
                        )

            # Classification select (simple accounts and all liabilities)
            with Horizontal(classes="acd-row", id="classification-row"):
                yield Label("Classification:", classes="acd-label")
                yield AppSelect(
                    _CLASSIFICATION_OPTIONS,
                    allow_blank=False,
                    id="classification-select",
                    classes="acd-field",
                )

            # Registration select (investment assets only; initially hidden)
            if self._side == "asset":
                with Horizontal(classes="acd-row", id="registration-row"):
                    yield Label("Registration:", classes="acd-label")
                    yield AppSelect(
                        _REGISTRATION_OPTIONS,
                        allow_blank=False,
                        id="registration-select",
                        classes="acd-field",
                    )

            # Owner checkboxes (pre-checked in edit mode)
            with Horizontal(classes="acd-owners-row"):
                yield Label("Owner(s):", classes="acd-label")
                with Vertical(id="owners-checks"):
                    for person in self._persons:
                        initial_checked = (
                            self._existing is not None and person.id in self._existing.owner_ids
                        )
                        yield AppCheckbox(
                            person.name,
                            value=initial_checked,
                            id=f"owner-{person.id}",
                        )

            # Action buttons
            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="btn-cancel")
                yield Button(
                    "Save" if is_edit else "Create",
                    id="btn-create",
                    variant="primary",
                )

    def on_mount(self) -> None:
        """Set initial field visibility, pre-populate selects in edit mode, and focus."""
        if self._side == "asset":
            self._sync_visibility()
        if self._existing is not None:
            self._prepopulate_selects()
        self.query_one("#acct-name", TextInput).focus()

    def on_radio_set_changed(self, event: AppRadioSet.Changed) -> None:
        """Swap Classification / Registration rows when Nature changes (create mode only)."""
        if event.radio_set.id == "nature-radio":
            self._sync_visibility()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Cancel or attempt account save."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-create":
            if self._existing is None:
                self._do_create()
            else:
                self._do_save()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _sync_visibility(self) -> None:
        """Show Classification or Registration based on the current Nature selection."""
        is_inv = self._is_investment()
        self.query_one("#classification-row").display = not is_inv
        if self._side == "asset":
            self.query_one("#registration-row").display = is_inv

    def _is_investment(self) -> bool:
        """Return True when the account is an Investment account."""
        if self._side != "asset":
            return False
        if self._existing is not None:
            return self._existing.is_investment
        try:
            return self.query_one("#nature-radio", AppRadioSet).pressed_index == 1
        except Exception:
            return False

    def _prepopulate_selects(self) -> None:
        """Pre-select Classification or Registration based on existing account data."""
        existing = self._existing
        assert existing is not None
        if existing.is_investment and existing.investment_registration is not None:
            try:
                self.query_one(
                    "#registration-select", AppSelect
                ).value = existing.investment_registration
            except Exception:
                pass
        elif not existing.is_investment and existing.simple_category is not None:
            try:
                self.query_one("#classification-select", AppSelect).value = existing.simple_category
            except Exception:
                pass

    def _collect_form_fields(
        self,
    ) -> (
        tuple[
            str, bool, bool, SimpleAccountCategory | None, InvestmentRegistration | None, list[int]
        ]
        | None
    ):
        """Validate and collect all form fields. Returns None if validation fails."""
        name = self.query_one("#acct-name", TextInput).value.strip()
        if not name:
            self.notify("Account name is required.", severity="error", timeout=3)
            self.query_one("#acct-name", TextInput).focus()
            return None

        is_long_term = self.query_one("#term-radio", AppRadioSet).pressed_index == 1

        is_inv = self._is_investment()
        simple_cat: SimpleAccountCategory | None = None
        inv_reg: InvestmentRegistration | None = None

        if is_inv:
            reg_val = self.query_one("#registration-select", AppSelect).value
            if reg_val is AppSelect.NULL:
                self.notify("Select a registration type.", severity="error", timeout=3)
                return None
            inv_reg = reg_val  # type: ignore[assignment]
        else:
            cat_val = self.query_one("#classification-select", AppSelect).value
            if cat_val is AppSelect.NULL:
                self.notify("Select a classification.", severity="error", timeout=3)
                return None
            simple_cat = cat_val  # type: ignore[assignment]

        selected_ids = [
            p.id for p in self._persons if self.query_one(f"#owner-{p.id}", AppCheckbox).value
        ]
        if not selected_ids:
            self.notify("Select at least one owner.", severity="error", timeout=3)
            return None

        return name, is_long_term, is_inv, simple_cat, inv_reg, selected_ids

    def _do_create(self) -> None:
        """Validate form inputs and call the service to create the account."""
        fields = self._collect_form_fields()
        if fields is None:
            return
        name, is_long_term, is_inv, simple_cat, inv_reg, selected_ids = fields

        if self._side == "asset":
            classification = (
                AccountClassification.ASSET_LONG_TERM
                if is_long_term
                else AccountClassification.ASSET_CURRENT
            )
        else:
            classification = (
                AccountClassification.LIABILITY_LONG_TERM
                if is_long_term
                else AccountClassification.LIABILITY_CURRENT
            )

        try:
            new_id: int = self.app.services.balance_sheet.create_account(  # type: ignore[attr-defined]
                name=name,
                classification=classification,
                nature="investment" if is_inv else "simple",
                simple_category=simple_cat,
                investment_registration=inv_reg,
                owner_ids=selected_ids,
                as_of=self.app.effective_date,  # type: ignore[attr-defined]
            )
            self.dismiss(new_id)
        except Exception as exc:
            logger.error("create_account_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to create account: {exc}", severity="error", timeout=5)

    def _do_save(self) -> None:
        """Validate form inputs and call the service to update the account metadata."""
        assert self._existing is not None
        fields = self._collect_form_fields()
        if fields is None:
            return
        name, is_long_term, _is_inv, simple_cat, inv_reg, selected_ids = fields

        try:
            self.app.services.balance_sheet.update_account_metadata(  # type: ignore[attr-defined]
                account_id=self._existing.account_id,
                name=name,
                is_long_term=is_long_term,
                simple_category=simple_cat,
                investment_registration=inv_reg,
                owner_ids=selected_ids,
            )
            self.dismiss(self._existing.account_id)
        except Exception as exc:
            logger.error("update_account_metadata_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save account: {exc}", severity="error", timeout=5)

    def action_cancel(self) -> None:
        """Esc closes the dialog without saving."""
        self.dismiss(None)


# ── AddHoldingDialog ──────────────────────────────────────────────────────


class AddHoldingDialog(ModalDialogMixin, ModalScreen[int | None]):
    """Modal dialog to add a listed security or exact holding — Flow F-7a.

    Yields the new holding's database ID on success, or ``None`` on cancel.

    The symbol search field accepts free text; pressing Enter triggers an async
    search via BS-OP-13. Up to five results are shown as individually-selectable
    radio buttons. Selecting one triggers a price fetch (BS-OP-13 / quote service)
    that populates the Unit Price and Total read-only fields. Total updates live
    as the user edits the Quantity input.

    Args:
        account_id: Primary key of the InvestmentAccount to add a holding to.
        asset_classes: Active asset classes to display in the allocation form.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = f"""
    AddHoldingDialog .dialog {{
        width: 90;
        height: 85vh;
    }}
    AddHoldingDialog #acd-scroll {{
        height: 1fr;
    }}
    AddHoldingDialog .acd-row {{
        height: 3;
        layout: horizontal;
    }}
    AddHoldingDialog .acd-label {{
        width: 22;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }}
    AddHoldingDialog .acd-field {{
        width: 20;
        height: 3;
    }}
    AddHoldingDialog RadioSet {{
        layout: horizontal;
        height: 3;
        border: none;
        background: transparent;
        padding: 0;
        width: 1fr;
        align: left middle;
    }}
    AddHoldingDialog RadioSet:focus {{
        border: none;
    }}
    AddHoldingDialog RadioButton {{
        background: transparent;
        height: 1;
        width: 1fr;
    }}
    AddHoldingDialog RadioButton:focus {{
        background: #0055cc;
    }}
    AddHoldingDialog #search-results {{
        height: auto;
        padding-left: 22;
    }}
    AddHoldingDialog #search-results RadioButton {{
        width: 100%;
        height: 1;
        background: transparent;
        border: none;
        color: #ffffff;
        padding: 0 1;
    }}
    AddHoldingDialog #search-results RadioButton:focus {{
        background: #0055cc;
        border: none;
        color: #ffffff;
    }}
    AddHoldingDialog .acd-static-value {{
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: #ffffff;
        padding: 0 1;
    }}
    AddHoldingDialog .acd-static-dim {{
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: {TEXT_DIM};
        padding: 0 1;
    }}
    AddHoldingDialog .acd-section-label {{
        color: #aaaaff;
        text-style: bold;
        height: 2;
        content-align: left bottom;
        padding-bottom: 0;
        margin-top: 1;
    }}
    AddHoldingDialog #listed-section {{
        height: auto;
    }}
    AddHoldingDialog #manual-section {{
        height: auto;
    }}
    """

    def __init__(
        self,
        account_id: int,
        asset_classes: list[AccountAssetClassOption],
    ) -> None:
        """Store the account ID and asset classes."""
        super().__init__()
        self._account_id = account_id
        self._asset_classes = asset_classes
        self._search_results: list[SecuritySearchResult] = []
        self._selected_result: SecuritySearchResult | None = None
        self._selected_rb: RadioButton | None = None
        self._unit_price: Decimal | None = None
        self._handling_rb_change = False

    def compose(self) -> ComposeResult:
        """Render the dialog layout."""
        with Vertical(classes="dialog"):
            yield Static("Add Holding", classes="dialog--title")
            with VerticalScroll(id="acd-scroll"):
                # Type selector
                with Horizontal(classes="acd-row"):
                    yield Label("Type:", classes="acd-label")
                    yield AppRadioSet(
                        RadioButton("Listed Security", value=True),
                        RadioButton("Manual Entry"),
                        id="type-radio",
                    )

                # ── Listed Security section ───────────────────────────────
                with Vertical(id="listed-section"):
                    with Horizontal(classes="acd-row"):
                        yield Label("Symbol:", classes="acd-label")
                        yield Input(id="symbol-input", classes="acd-field")
                    # Search results — hidden until a search completes
                    with Vertical(id="search-results"):
                        pass  # RadioButtons mounted dynamically
                    with Horizontal(classes="acd-row"):
                        yield Label("Quantity:", classes="acd-label")
                        yield QuantityInput(id="quantity-input", classes="acd-field")
                    with Horizontal(classes="acd-row"):
                        yield Label("Name:", classes="acd-label")
                        yield Static("—", id="selected-name", classes="acd-static-dim")
                    with Horizontal(classes="acd-row"):
                        yield Label("Unit Price:", classes="acd-label")
                        yield Static("—", id="unit-price-display", classes="acd-static-dim")
                    with Horizontal(classes="acd-row"):
                        yield Label("Total:", classes="acd-label")
                        yield Static("—", id="total-display", classes="acd-static-dim")

                # ── Manual Entry section (hidden initially) ───────────────
                with Vertical(id="manual-section"):
                    with Horizontal(classes="acd-row"):
                        yield Label("Name:", classes="acd-label")
                        yield TextInput(id="manual-name", classes="acd-field")
                    with Horizontal(classes="acd-row"):
                        yield Label("Total:", classes="acd-label")
                        yield MoneyInput(
                            id="manual-amount",
                            classes="acd-field",
                            placeholder="$ 0.00",
                        )

                # ── Asset Allocation (both types) ─────────────────────────
                yield Static("Asset Allocation", classes="acd-section-label")
                yield AssetAllocationForm(self._asset_classes, id="alloc-form")

            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="btn-cancel")
                yield Button("Create", id="btn-create", variant="primary", disabled=True)

    def on_mount(self) -> None:
        """Hide the manual section initially and focus the symbol input."""
        self.query_one("#manual-section").display = False
        self.query_one("#search-results").display = False
        self.query_one("#symbol-input", Input).focus()

    # ── Type radio ────────────────────────────────────────────────────────

    def on_radio_set_changed(self, event: AppRadioSet.Changed) -> None:
        """Toggle between listed and manual sections when the type radio changes."""
        if event.radio_set.id != "type-radio":
            return
        is_listed = event.radio_set.pressed_index == 0
        self.query_one("#listed-section").display = is_listed
        self.query_one("#manual-section").display = not is_listed
        if is_listed:
            self.query_one("#symbol-input", Input).focus()
        else:
            self.query_one("#manual-name", Input).focus()

    # ── Symbol search ─────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dispatch input submissions by widget ID."""
        input_id = event.input.id
        event.stop()
        if input_id == "symbol-input":
            query = event.value.strip()
            if query:
                self.run_worker(
                    self._do_search(query),
                    exclusive=False,
                    name="symbol-search",
                )
        elif input_id == "quantity-input":
            self._recalculate_total()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Recalculate the live Total when the quantity input changes."""
        if event.input.id == "quantity-input":
            event.stop()
            self._recalculate_total()

    def _refocus_symbol_input(self, _result: object) -> None:
        """Return focus to the symbol input after an error dialog is dismissed."""
        self.query_one("#symbol-input", Input).focus()

    async def _do_search(self, query: str) -> None:
        """Run a symbol search and populate the results list."""
        results_container = self.query_one("#search-results")
        try:
            results: list[SecuritySearchResult] = (
                await self.app.services.balance_sheet.search_symbols(query)  # type: ignore[attr-defined]
            )
        except QuoteServiceError as exc:
            logger.error("symbol_search_failed", error=str(exc))
            self.app.push_screen(
                ErrorDialog(f"Symbol search failed: {exc}", title="Search Error"),
                callback=self._refocus_symbol_input,
            )
            return

        if not results:
            self.app.push_screen(
                ErrorDialog(
                    "No securities found. Try a different symbol or name.",
                    title="No Results",
                ),
                callback=self._refocus_symbol_input,
            )
            return

        self._search_results = results
        self._selected_result = None
        self._selected_rb = None
        self._unit_price = None
        self._reset_selected_info()

        await results_container.remove_children()
        for i, result in enumerate(results):
            label = f"{result.symbol} — {result.name} ({result.exchange})"
            await results_container.mount(RadioButton(label, value=False, id=f"sr-{i}"))
        results_container.display = True

        # Focus the first result
        try:
            results_container.query(RadioButton).first(RadioButton).focus()
        except Exception:
            pass

    # ── Search result selection ───────────────────────────────────────────

    def on_radio_button_changed(self, event: RadioButton.Changed) -> None:
        """Handle search result radio button selection with manual mutual exclusion."""
        rb = event.radio_button
        if not rb.id or not rb.id.startswith("sr-"):
            return
        if self._handling_rb_change:
            return
        if not event.value:
            # User deselected the active button; clear state
            if rb is self._selected_rb:
                self._selected_rb = None
                self._selected_result = None
                self._unit_price = None
                self._reset_selected_info()
            return
        # A new result was selected — deselect the previous one
        self._handling_rb_change = True
        try:
            if self._selected_rb is not None and self._selected_rb is not rb:
                self._selected_rb.value = False
        finally:
            self._handling_rb_change = False

        idx = int(rb.id[3:])
        self._selected_rb = rb
        self._selected_result = self._search_results[idx]
        self._unit_price = None

        # Show name immediately; fetch price asynchronously; move focus to Quantity
        self._set_selected_name(self._selected_result.name)
        self.query_one("#unit-price-display", Static).update("Loading…")
        self.query_one("#unit-price-display", Static).set_class(False, "acd-static-dim")
        self.query_one("#unit-price-display", Static).set_class(True, "acd-static-value")
        self.query_one("#total-display", Static).update("—")
        self.query_one("#total-display", Static).set_class(True, "acd-static-dim")
        self.query_one("#total-display", Static).set_class(False, "acd-static-value")

        self.query_one("#quantity-input", Input).focus()

        self.run_worker(
            self._do_fetch_price(self._selected_result.symbol),
            exclusive=False,
            name="fetch-price",
        )

    async def _do_fetch_price(self, symbol: str) -> None:
        """Fetch the unit price for the selected symbol and update the display."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        try:
            price: Decimal = await self.app.services.balance_sheet.get_unit_price(  # type: ignore[attr-defined]
                symbol, as_of
            )
        except QuoteServiceError as exc:
            logger.error("price_fetch_failed", symbol=symbol, error=str(exc))
            self.query_one("#unit-price-display", Static).update(f"Error: {exc}")
            return
        except Exception as exc:
            logger.error("price_fetch_unexpected", symbol=symbol, error=str(exc))
            self.query_one("#unit-price-display", Static).update("Unavailable")
            return

        # Only apply if this result is still the selected one
        if self._selected_result is None or self._selected_result.symbol != symbol:
            return

        self._unit_price = price
        self.query_one("#unit-price-display", Static).update(MoneyInput.format(price))
        self._recalculate_total()

    # ── Allocation form ───────────────────────────────────────────────────

    def on_asset_allocation_form_changed(self, event: AssetAllocationForm.Changed) -> None:
        """Enable or disable [Create] based on whether allocations sum to 100%."""
        event.stop()
        self.query_one("#btn-create", Button).disabled = not event.is_valid

    # ── Buttons ───────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Cancel or attempt holding creation."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-create":
            self._do_create()

    # ── Actions ───────────────────────────────────────────────────────────

    def action_cancel(self) -> None:
        """Esc closes the dialog without saving."""
        self.dismiss(None)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _is_listed_type(self) -> bool:
        """Return True when the Listed Security radio is selected."""
        return self.query_one("#type-radio", AppRadioSet).pressed_index == 0

    def _set_selected_name(self, name: str) -> None:
        """Update the Name static with an active style."""
        widget = self.query_one("#selected-name", Static)
        widget.update(name)
        widget.set_class(False, "acd-static-dim")
        widget.set_class(True, "acd-static-value")

    def _reset_selected_info(self) -> None:
        """Reset Name, Unit Price, and Total back to their empty state."""
        for widget_id in ("selected-name", "unit-price-display", "total-display"):
            w = self.query_one(f"#{widget_id}", Static)
            w.update("—")
            w.set_class(True, "acd-static-dim")
            w.set_class(False, "acd-static-value")

    def _recalculate_total(self) -> None:
        """Recompute Total from unit price × quantity and update the display."""
        if self._unit_price is None:
            return
        try:
            qty = QuantityInput.parse(self.query_one("#quantity-input", QuantityInput).value)
            if qty > 0:
                total = self._unit_price * qty
                w = self.query_one("#total-display", Static)
                w.update(MoneyInput.format(total))
                w.set_class(False, "acd-static-dim")
                w.set_class(True, "acd-static-value")
            else:
                self.query_one("#total-display", Static).update("—")
        except (InvalidOperation, Exception):
            self.query_one("#total-display", Static).update("—")

    def _do_create(self) -> None:
        """Validate all inputs and call the service to create the holding."""
        alloc_form = self.query_one("#alloc-form", AssetAllocationForm)
        if not alloc_form.is_valid():
            self.notify("Asset allocation must sum to 100%.", severity="error", timeout=3)
            return

        allocations = alloc_form.get_allocations()
        as_of = self.app.effective_date  # type: ignore[attr-defined]

        try:
            if self._is_listed_type():
                if self._selected_result is None:
                    self.notify(
                        "Select a security from the search results.",
                        severity="error",
                        timeout=3,
                    )
                    return
                raw_qty = self.query_one("#quantity-input", QuantityInput).value
                try:
                    qty = QuantityInput.parse(raw_qty)
                except InvalidOperation:
                    self.notify("Quantity must be a number.", severity="error", timeout=3)
                    return
                if qty <= 0:
                    self.notify("Quantity must be positive.", severity="error", timeout=3)
                    return
                new_id = self.app.services.balance_sheet.add_holding(  # type: ignore[attr-defined]
                    account_id=self._account_id,
                    holding_type="listed",
                    name=self._selected_result.name,
                    as_of=as_of,
                    symbol=self._selected_result.symbol,
                    initial_quantity=qty,
                    initial_amount=None,
                    allocations=allocations,
                )
            else:
                name = self.query_one("#manual-name", TextInput).value.strip()
                if not name:
                    self.notify("Name is required.", severity="error", timeout=3)
                    return
                raw_amount = self.query_one("#manual-amount", MoneyInput).value
                try:
                    amount = MoneyInput.parse(raw_amount)
                except InvalidOperation:
                    self.notify("Total must be a number.", severity="error", timeout=3)
                    return
                new_id = self.app.services.balance_sheet.add_holding(  # type: ignore[attr-defined]
                    account_id=self._account_id,
                    holding_type="exact",
                    name=name,
                    as_of=as_of,
                    symbol=None,
                    initial_quantity=None,
                    initial_amount=amount,
                    allocations=allocations,
                )

            self.dismiss(new_id)

        except Exception as exc:
            logger.error("add_holding_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to create holding: {exc}", severity="error", timeout=5)


# ── HoldingAllocationDialog ───────────────────────────────────────────────


class HoldingAllocationDialog(ModalDialogMixin, ModalScreen[bool]):
    """Modal dialog to edit the asset allocation for an existing holding — Flow F-7b.

    Dismisses with ``True`` on a successful save, ``False`` on cancel.

    Args:
        holding_id: Primary key of the holding to update.
        asset_classes: Active asset classes to display in the allocation form.
        initial_allocations: Current allocation mapping of asset_class_id → percent.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        holding_id: int,
        asset_classes: list[AccountAssetClassOption],
        initial_allocations: dict[int, Decimal],
    ) -> None:
        """Store holding id, asset classes, and initial allocation values."""
        super().__init__()
        self._holding_id = holding_id
        self._asset_classes = asset_classes
        self._initial_allocations = initial_allocations

    def compose(self) -> ComposeResult:
        """Render the allocation form and action buttons."""
        with Vertical(classes="dialog"):
            yield Static("Edit Asset Allocation", classes="dialog--title")
            with VerticalScroll():
                yield AssetAllocationForm(
                    self._asset_classes,
                    self._initial_allocations,
                    id="cad-alloc-form",
                )
            with Horizontal(classes="dialog--buttons"):
                yield Button("Cancel", id="cad-cancel", variant="default")
                yield Button("Save", id="cad-save", variant="primary", disabled=True)

    def on_mount(self) -> None:
        """Enable Save if allocations already sum to 100%; focus the first input."""
        alloc_form = self.query_one("#cad-alloc-form", AssetAllocationForm)
        self.query_one("#cad-save", Button).disabled = not alloc_form.is_valid()
        alloc_form.focus_first_input()

    def on_asset_allocation_form_changed(self, event: AssetAllocationForm.Changed) -> None:
        """Enable or disable [Save] based on whether allocations sum to 100%."""
        self.query_one("#cad-save", Button).disabled = not event.is_valid

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle Cancel or Save."""
        if event.button.id == "cad-cancel":
            self.dismiss(False)
        elif event.button.id == "cad-save":
            self.run_worker(self._do_save(), exclusive=False, name="save-allocation")

    def action_cancel(self) -> None:
        """Dismiss without saving (Escape)."""
        self.dismiss(False)

    async def _do_save(self) -> None:
        """BS-OP-12: Persist the updated allocation and dismiss on success."""
        as_of = self.app.effective_date  # type: ignore[attr-defined]
        allocations = self.query_one("#cad-alloc-form", AssetAllocationForm).get_allocations()
        try:
            self.app.services.balance_sheet.update_holding_asset_allocation(  # type: ignore[attr-defined]
                self._holding_id, as_of, allocations
            )
            self.dismiss(True)
        except Exception as exc:
            logger.error("update_allocation_failed", error=str(exc), exc_info=True)
            self.notify(f"Failed to save allocation: {exc}", severity="error", timeout=5)
