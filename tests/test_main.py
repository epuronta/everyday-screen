"""Tests for the display route helpers in app.main."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app import settings
from app.main import (
    IMAGE_CACHE_TTL,
    _battery_label,
    _CacheEntry,
    _fi_date,
    _interval_label,
    _next_refresh_seconds,
    _today_dishes,
)
from app.menu import Dish, MenuDay


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (datetime(2026, 1, 5, tzinfo=UTC), "Maanantai 5.1. (tammikuu)"),
        (datetime(2026, 6, 7, tzinfo=UTC), "Sunnuntai 7.6. (kesäkuu)"),
        (datetime(2026, 8, 27, tzinfo=UTC), "Torstai 27.8. (elokuu)"),
        (datetime(2026, 12, 31, tzinfo=UTC), "Torstai 31.12. (joulukuu)"),
    ],
)
def test_fi_date_formats_weekday_day_and_month(dt: datetime, expected: str) -> None:
    assert _fi_date(dt) == expected


def test_fi_date_ignores_the_time_of_day() -> None:
    midnight = datetime(2026, 8, 27, 0, 0, tzinfo=UTC)
    late = datetime(2026, 8, 27, 23, 59, tzinfo=UTC)
    assert _fi_date(midnight) == _fi_date(late)


# _fi_date takes whatever datetime it is handed and formats its naive fields, so
# callers are responsible for converting to local time first (app.main does this
# in _build_context).
def test_fi_date_does_not_convert_timezones() -> None:
    # 00:30 UTC on the 27th is already 03:30 on the 27th in Helsinki, but an
    # unconverted UTC value one hour earlier still formats as the 26th.
    assert _fi_date(datetime(2026, 8, 26, 23, 30, tzinfo=UTC)) == (
        "Keskiviikko 26.8. (elokuu)"
    )


TODAY = date(2026, 8, 27)


def _day(day: date, *names: str) -> MenuDay:
    return MenuDay(date=day, dishes=[Dish(name=n) for n in names])


def test_today_dishes_returns_the_matching_days_dishes() -> None:
    days = [
        _day(date(2026, 8, 26), "eilinen"),
        _day(TODAY, "lohikeitto", "salaatti"),
        _day(date(2026, 8, 28), "huominen"),
    ]
    dishes = _today_dishes(days, TODAY)
    assert dishes is not None
    assert [d.name for d in dishes] == ["lohikeitto", "salaatti"]


def test_today_dishes_returns_none_when_days_is_none() -> None:
    assert _today_dishes(None, TODAY) is None


def test_today_dishes_returns_none_for_an_empty_list() -> None:
    assert _today_dishes([], TODAY) is None


def test_today_dishes_returns_none_when_today_is_absent() -> None:
    assert _today_dishes([_day(date(2026, 8, 28), "huominen")], TODAY) is None


def test_today_dishes_returns_none_when_the_day_has_no_dishes() -> None:
    """An empty dish list is normalised to None so the template can skip the block."""
    assert _today_dishes([_day(TODAY)], TODAY) is None


def test_today_dishes_returns_the_first_match_only() -> None:
    days = [_day(TODAY, "eka"), _day(TODAY, "toka")]
    dishes = _today_dishes(days, TODAY)
    assert dishes is not None
    assert [d.name for d in dishes] == ["eka"]


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def test_cache_entry_is_fresh_immediately() -> None:
    assert _CacheEntry(data=b"png", time=NOW).is_fresh(NOW)


def test_cache_entry_is_fresh_just_before_the_ttl() -> None:
    entry = _CacheEntry(data=b"png", time=NOW)
    assert entry.is_fresh(NOW + IMAGE_CACHE_TTL - timedelta(seconds=1))


def test_cache_entry_expires_exactly_at_the_ttl() -> None:
    """The comparison is a strict <, so the TTL boundary itself counts as stale."""
    entry = _CacheEntry(data=b"png", time=NOW)
    assert not entry.is_fresh(NOW + IMAGE_CACHE_TTL)


def test_cache_entry_is_stale_after_the_ttl() -> None:
    entry = _CacheEntry(data=b"png", time=NOW)
    assert not entry.is_fresh(NOW + IMAGE_CACHE_TTL + timedelta(seconds=1))


def test_next_refresh_seconds_follows_the_schedule(monkeypatch) -> None:
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 0)
    # 04:00 UTC is 07:00 in Helsinki in August - the 3-minute morning band.
    assert _next_refresh_seconds(datetime(2026, 8, 27, 4, 0, tzinfo=UTC)) == 180


def test_next_refresh_seconds_honours_the_dev_override(monkeypatch) -> None:
    """A dev instance shouldn't make you wait out a 10-minute band."""
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 60)
    assert _next_refresh_seconds(datetime(2026, 8, 27, 12, 0, tzinfo=UTC)) == 60


@pytest.mark.parametrize(
    ("voltage", "expected"),
    [
        (4.2, "4.20 V (100 %)"),
        (3.9, "3.90 V (75 %)"),
        (3.6, "3.60 V (50 %)"),
        (3.01, "3.01 V (1 %)"),
        (4.5, "4.50 V (100 %)"),
    ],
)
def test_battery_label_pairs_voltage_with_a_percentage(
    voltage: float, expected: str
) -> None:
    """The percentage is known to read low, so the raw voltage rides along."""
    assert _battery_label(voltage) == expected


def test_battery_label_reports_usb_power() -> None:
    """readBattery() returns near zero off the battery, same as the firmware did."""
    assert _battery_label(3.0) == "USB"
    assert _battery_label(0.0) == "USB"


def test_battery_label_is_empty_when_not_reported() -> None:
    """Browsers and `make screenshot` don't send one."""
    assert _battery_label(None) == ""


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(180, "3 min"), (600, "10 min"), (1800, "30 min"), (60, "1 min"), (30, "30 s")],
)
def test_interval_label(seconds: int, expected: str) -> None:
    assert _interval_label(seconds) == expected
