"""Tests for the Amica page scraping in app.menu_amica."""

from datetime import date
from pathlib import Path

import pytest

from app.menu_amica import _parse

FIXTURES = Path(__file__).parent / "fixtures"


def _page() -> str:
    return (FIXTURES / "amica_menu.html").read_text(encoding="utf-8")


def test_parses_the_lunch_days() -> None:
    days = _parse(_page())
    assert [d.date for d in days] == [date(2026, 8, 27), date(2026, 8, 28)]


def test_keeps_only_the_lounas_package() -> None:
    """The salad bar and other packages are noise on a one-line display."""
    days = _parse(_page())
    assert [d.name for d in days[0].dishes] == ["Lohikeitto", "Ruisleipä"]


def test_strips_whitespace_from_dish_names() -> None:
    assert _parse(_page())[0].dishes[0].name == "Lohikeitto"


def test_skips_days_with_no_meals() -> None:
    """Holidays come back as a day with an empty meal list."""
    assert date(2026, 8, 29) not in [d.date for d in _parse(_page())]


def test_reads_the_date_without_the_time_component() -> None:
    assert _parse(_page())[0].date == date(2026, 8, 27)


def test_handles_nested_braces_in_the_payload() -> None:
    """The regex is anchored to </script> so nesting doesn't truncate it."""
    days = _parse(_page())
    assert len(days[0].dishes) == 2


def test_raises_when_the_payload_is_missing() -> None:
    with pytest.raises(ValueError, match="__INITIAL_MENU__ not found"):
        _parse("<html><body>no menu here</body></html>")
