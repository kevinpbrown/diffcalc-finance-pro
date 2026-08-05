"""Reusable asset-allocation form widget — used by F-7a and F-7b."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static

from personal_finance.service.application.balance_sheet_app_service import (
    AccountAssetClassOption,
    AllocationInput,
)
from personal_finance.ui.widgets.inputs import PercentInput


class AssetAllocationForm(Widget):
    """Editable list of asset-class percentage inputs with a live running total.

    Emits :class:`AssetAllocationForm.Changed` whenever any input is modified,
    carrying an ``is_valid`` flag indicating whether the percentages sum to 100.

    The :meth:`get_allocations` method returns the current values as a list of
    :class:`AllocationInput` objects ready to pass to the app service layer.

    Args:
        asset_classes: Ordered list of active asset classes to display.
        initial_allocations: Optional mapping of asset-class ID → initial percent.
            Defaults to 0 for any class not present in the mapping.
    """

    class Changed(Message):
        """Posted whenever any allocation input changes.

        Attributes:
            is_valid: True when all percentages sum exactly to 100.
        """

        def __init__(self, is_valid: bool) -> None:
            """Store validity flag."""
            super().__init__()
            self.is_valid = is_valid

    DEFAULT_CSS = """
    AssetAllocationForm {
        height: auto;
    }
    AssetAllocationForm .aaf-row {
        height: 3;
        layout: horizontal;
    }
    AssetAllocationForm .aaf-label {
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: #aaaaaa;
    }
    AssetAllocationForm .aaf-input {
        width: 13;
        height: 3;
    }
    AssetAllocationForm .aaf-total-row {
        height: 1;
        layout: horizontal;
        margin-top: 1;
        margin-bottom: 1;
    }
    AssetAllocationForm .aaf-total-label {
        width: 1fr;
        content-align: left middle;
        color: #aaaaaa;
    }
    AssetAllocationForm #aaf-total-value {
        width: 13;
        content-align: right middle;
        color: #ffffff;
    }
    AssetAllocationForm #aaf-total-value.aaf-invalid {
        color: #ff4444;
    }
    """

    def __init__(
        self,
        asset_classes: list[AccountAssetClassOption],
        initial_allocations: dict[int, Decimal] | None = None,
        *,
        id: str | None = None,
    ) -> None:
        """Store asset classes and optional initial values."""
        super().__init__(id=id)
        self._asset_classes = asset_classes
        self._initial = initial_allocations or {}

    def compose(self) -> ComposeResult:
        """Render one input row per asset class, followed by a total row."""
        for ac in self._asset_classes:
            initial = self._initial.get(ac.id, Decimal("0"))
            with Horizontal(classes="aaf-row"):
                yield Static(ac.name, classes="aaf-label")
                yield PercentInput(
                    value=PercentInput.format(initial),
                    id=f"aaf-{ac.id}",
                    classes="aaf-input",
                )
        with Horizontal(classes="aaf-total-row"):
            yield Static("Total:", classes="aaf-total-label")
            yield Static("0%", id="aaf-total-value", classes="aaf-invalid")

    def on_mount(self) -> None:
        """Compute and display the initial total."""
        self._refresh_total()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Recompute the total and post Changed when any allocation input changes."""
        if event.input.id and event.input.id.startswith("aaf-"):
            event.stop()
            self._refresh_total()

    def is_valid(self) -> bool:
        """Return True when all percentages sum exactly to 100."""
        return self._compute_total() == Decimal("100")

    def get_allocations(self) -> list[AllocationInput]:
        """Return current allocation values as app-service DTOs.

        Returns:
            One :class:`AllocationInput` per asset class in display order.
            Inputs that cannot be parsed default to 0%.
        """
        result = []
        for ac in self._asset_classes:
            try:
                inp = self.query_one(f"#aaf-{ac.id}", PercentInput)
                pct = PercentInput.parse(inp.value)
            except (InvalidOperation, Exception):
                pct = Decimal("0")
            result.append(AllocationInput(asset_class_id=ac.id, percent=pct))
        return result

    def focus_first_input(self) -> None:
        """Focus the first asset-class percentage input."""
        if self._asset_classes:
            self.query_one(f"#aaf-{self._asset_classes[0].id}", Input).focus()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _compute_total(self) -> Decimal:
        """Sum all allocation inputs, ignoring unparseable values."""
        total = Decimal("0")
        for ac in self._asset_classes:
            try:
                inp = self.query_one(f"#aaf-{ac.id}", PercentInput)
                total += PercentInput.parse(inp.value)
            except (InvalidOperation, Exception):
                pass
        return total

    def _refresh_total(self) -> None:
        """Update the total display and post a Changed message."""
        total = self._compute_total()
        total_widget = self.query_one("#aaf-total-value", Static)
        total_widget.update(PercentInput.format(total))
        valid = total == Decimal("100")
        if valid:
            total_widget.remove_class("aaf-invalid")
        else:
            total_widget.add_class("aaf-invalid")
        self.post_message(self.Changed(is_valid=valid))
