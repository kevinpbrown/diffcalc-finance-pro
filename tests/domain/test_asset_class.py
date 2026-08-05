"""Tests for AccountAssetClass.is_active()."""

from datetime import date

from personal_finance.domain.asset_class import AccountAssetClass


def _asset_class(date_created: date, date_disabled: date | None = None) -> AccountAssetClass:
    return AccountAssetClass(
        name="Equity",
        order_precedence=1,
        date_created=date_created,
        date_disabled=date_disabled,
    )


class TestIsActive:
    """AccountAssetClass.is_active() boundary conditions."""

    # ── date_created boundary ─────────────────────────────────────────────────

    def test_active_when_created_on_query_date(self) -> None:
        ac = _asset_class(date(2024, 1, 1))
        assert ac.is_active(date(2024, 1, 1)) is True

    def test_active_when_created_before_query_date(self) -> None:
        ac = _asset_class(date(2024, 1, 1))
        assert ac.is_active(date(2024, 6, 1)) is True

    def test_inactive_when_created_after_query_date(self) -> None:
        ac = _asset_class(date(2024, 6, 1))
        assert ac.is_active(date(2024, 1, 1)) is False

    # ── no date_disabled ──────────────────────────────────────────────────────

    def test_active_indefinitely_when_not_disabled(self) -> None:
        ac = _asset_class(date(2020, 1, 1), date_disabled=None)
        assert ac.is_active(date(2099, 12, 31)) is True

    # ── date_disabled boundary ────────────────────────────────────────────────

    def test_inactive_when_disabled_on_query_date(self) -> None:
        """date_disabled is exclusive — the asset class is no longer active on that date."""
        ac = _asset_class(date(2024, 1, 1), date_disabled=date(2024, 6, 1))
        assert ac.is_active(date(2024, 6, 1)) is False

    def test_active_one_day_before_disabled(self) -> None:
        ac = _asset_class(date(2024, 1, 1), date_disabled=date(2024, 6, 1))
        assert ac.is_active(date(2024, 5, 31)) is True

    def test_inactive_after_disabled_date(self) -> None:
        ac = _asset_class(date(2024, 1, 1), date_disabled=date(2024, 6, 1))
        assert ac.is_active(date(2024, 12, 31)) is False

    # ── combined edge case ────────────────────────────────────────────────────

    def test_inactive_when_created_after_and_disabled_in_future(self) -> None:
        """date_created check takes precedence — must satisfy both conditions."""
        ac = _asset_class(date(2025, 1, 1), date_disabled=date(2026, 1, 1))
        assert ac.is_active(date(2024, 6, 1)) is False
