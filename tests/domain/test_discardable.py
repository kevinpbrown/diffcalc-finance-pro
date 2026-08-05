"""Tests for the Discardable domain mixin."""

from datetime import date

import pytest

from personal_finance.domain.base import Discardable

CREATED = date(2024, 1, 1)
EFFECTIVE = date(2024, 3, 1)


class _Stub(Discardable):
    """Minimal concrete class used to exercise Discardable in isolation."""

    def __init__(
        self,
        date_effective: date = EFFECTIVE,
        date_modified: date = CREATED,
        date_discarded: date | None = None,
    ) -> None:
        self.date_effective = date_effective
        self.date_modified = date_modified
        self.date_discarded = date_discarded


class TestIsDiscarded:
    def test_false_when_not_discarded(self) -> None:
        assert _Stub(date_discarded=None).is_discarded is False

    def test_true_when_discarded(self) -> None:
        assert _Stub(date_discarded=date(2024, 6, 1)).is_discarded is True


class TestDiscard:
    def test_sets_date_discarded(self) -> None:
        stub = _Stub()
        stub.discard(date(2024, 6, 1))
        assert stub.date_discarded == date(2024, 6, 1)

    def test_is_discarded_true_after_discard(self) -> None:
        stub = _Stub()
        stub.discard(date(2024, 6, 1))
        assert stub.is_discarded is True

    def test_allows_discard_on_date_effective(self) -> None:
        stub = _Stub(date_effective=date(2024, 3, 1))
        stub.discard(date(2024, 3, 1))
        assert stub.date_discarded == date(2024, 3, 1)

    def test_raises_when_as_of_before_date_effective(self) -> None:
        stub = _Stub(date_effective=date(2024, 3, 1))
        with pytest.raises(ValueError, match="effective date"):
            stub.discard(date(2024, 2, 1))

    def test_raises_when_already_discarded_on_same_date(self) -> None:
        stub = _Stub(date_discarded=date(2024, 6, 1))
        with pytest.raises(ValueError, match="already discarded"):
            stub.discard(date(2024, 6, 1))

    def test_raises_when_already_discarded_and_as_of_is_later(self) -> None:
        stub = _Stub(date_discarded=date(2024, 6, 1))
        with pytest.raises(ValueError, match="already discarded"):
            stub.discard(date(2024, 7, 1))

    def test_moves_discard_date_earlier_when_already_discarded(self) -> None:
        stub = _Stub(date_discarded=date(2024, 6, 1))
        stub.discard(date(2024, 5, 1))
        assert stub.date_discarded == date(2024, 5, 1)

    def test_error_message_includes_class_name(self) -> None:
        stub = _Stub(date_discarded=date(2024, 6, 1))
        with pytest.raises(ValueError, match="_Stub"):
            stub.discard(date(2024, 6, 1))
