"""Tests for the Aromi API response parsing in app.menu_aromi."""

from datetime import date

from app.menu_aromi import _parse_days


def _meal(name: str, *dishes: str) -> dict:
    return {"MealName": name, "Dishes": [{"DishName": d} for d in dishes]}


def _day(day: str, *meals: dict) -> dict:
    return {"Date": f"{day}T00:00:00", "Meals": list(meals)}


def test_parses_a_days_dishes() -> None:
    raw = [_day("2026-08-27", _meal("Lounas.", "Jauhelihakastike", "Peruna"))]
    days = _parse_days(raw)
    assert len(days) == 1
    assert days[0].date == date(2026, 8, 27)
    assert [d.name for d in days[0].dishes] == ["Jauhelihakastike", "Peruna"]


def test_keeps_only_the_meat_option() -> None:
    """'Lounas.' with the period is the meat option; 'Lounas' is vegetarian."""
    raw = [
        _day(
            "2026-08-27",
            _meal("Lounas", "Kasvislasagne"),
            _meal("Lounas.", "Lihapullat"),
            _meal("Jälkiruoka", "Kiisseli"),
        )
    ]
    assert [d.name for d in _parse_days(raw)[0].dishes] == ["Lihapullat"]


def test_merges_dishes_across_several_matching_meals() -> None:
    raw = [
        _day("2026-08-27", _meal("Lounas.", "Keitto"), _meal("Lounas.", "Leipä")),
    ]
    assert [d.name for d in _parse_days(raw)[0].dishes] == ["Keitto", "Leipä"]


def test_strips_whitespace_from_dish_names() -> None:
    raw = [_day("2026-08-27", _meal("Lounas.", "  Kalapuikot  "))]
    assert _parse_days(raw)[0].dishes[0].name == "Kalapuikot"


def test_skips_days_with_no_relevant_meals() -> None:
    raw = [
        _day("2026-08-27", _meal("Lounas", "Kasvislasagne")),
        _day("2026-08-28", _meal("Lounas.", "Lihapullat")),
    ]
    assert [d.date for d in _parse_days(raw)] == [date(2026, 8, 28)]


def test_handles_a_null_meals_list() -> None:
    """Weekends and holidays come back with Meals: null."""
    assert _parse_days([{"Date": "2026-08-29T00:00:00", "Meals": None}]) == []


def test_handles_a_missing_meals_key() -> None:
    assert _parse_days([{"Date": "2026-08-29T00:00:00"}]) == []


def test_handles_a_null_dish_list() -> None:
    raw = [_day("2026-08-27", {"MealName": "Lounas.", "Dishes": None})]
    assert _parse_days(raw) == []


def test_handles_an_empty_response() -> None:
    assert _parse_days([]) == []
