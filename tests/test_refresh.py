"""Tests for the refresh schedule in app.refresh."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.refresh import MIN_INTERVAL, next_refresh

HELSINKI = ZoneInfo("Europe/Helsinki")

THREE_MIN = timedelta(minutes=3)
TEN_MIN = timedelta(minutes=10)
THIRTY_MIN = timedelta(minutes=30)


def _at(hour: int, minute: int = 0, second: int = 0, *, day: int = 27) -> datetime:
    """Build a local Helsinki time in August, clear of DST transitions."""
    return datetime(2026, 8, day, hour, minute, second, tzinfo=HELSINKI)


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        (_at(6, 0), THREE_MIN),
        (_at(7, 30), THREE_MIN),
        (_at(8, 0), THREE_MIN),
        (_at(9, 0), TEN_MIN),
        (_at(12, 0), TEN_MIN),
        (_at(17, 0), TEN_MIN),
        (_at(21, 0), TEN_MIN),
        (_at(22, 0), THIRTY_MIN),
        (_at(23, 30), THIRTY_MIN),
        (_at(0, 30), THIRTY_MIN),
        (_at(3, 0), THIRTY_MIN),
    ],
)
def test_band_intervals(local: datetime, expected: timedelta) -> None:
    assert next_refresh(local, HELSINKI) == expected


def test_bands_are_the_same_every_day_of_the_week() -> None:
    """Weekday/weekend was collapsed away - the numbers turned out identical."""
    # 24th is a Monday, 29th a Saturday, 30th a Sunday.
    for day in (24, 29, 30):
        assert next_refresh(_at(7, 0, day=day), HELSINKI) == THREE_MIN
        assert next_refresh(_at(14, 0, day=day), HELSINKI) == TEN_MIN
        assert next_refresh(_at(23, 0, day=day), HELSINKI) == THIRTY_MIN


def test_night_clamps_to_the_start_of_the_morning_band() -> None:
    """Without the clamp, 05:45 sleeps through the first 15 tight minutes."""
    assert next_refresh(_at(5, 45), HELSINKI) == timedelta(minutes=15)


def test_morning_clamps_to_the_start_of_the_day_band() -> None:
    assert next_refresh(_at(8, 58), HELSINKI) == timedelta(minutes=2)


def test_evening_clamps_to_the_start_of_the_night_band() -> None:
    assert next_refresh(_at(21, 55), HELSINKI) == timedelta(minutes=5)


def test_a_clamp_never_returns_less_than_the_minimum() -> None:
    """08:59:30 is 30s from the boundary; waking then costs more than it saves."""
    assert next_refresh(_at(8, 59, 30), HELSINKI) == MIN_INTERVAL


def test_the_last_night_wake_lands_on_the_boundary() -> None:
    assert next_refresh(_at(5, 59), HELSINKI) == MIN_INTERVAL


def test_no_clamp_when_the_next_wake_stays_inside_the_band() -> None:
    assert next_refresh(_at(8, 50), HELSINKI) == THREE_MIN


def test_night_crosses_midnight_without_clamping() -> None:
    """23:50 + 30min is 00:20, still night - midnight is not a band edge."""
    assert next_refresh(_at(23, 50), HELSINKI) == THIRTY_MIN


def test_accepts_a_utc_now_and_converts_for_the_band_lookup() -> None:
    """The route passes UTC; 04:00 UTC is 07:00 in Helsinki in August."""
    assert next_refresh(datetime(2026, 8, 27, 4, 0, tzinfo=UTC), HELSINKI) == THREE_MIN


# Helsinki springs forward on 2026-03-29 (03:00 -> 04:00) and falls back on
# 2026-10-25 (04:00 -> 03:00). Boundaries are resolved in local time, so the
# returned duration has to stay a correct absolute measurement either way.
def test_clamp_is_correct_on_the_spring_forward_day() -> None:
    local = datetime(2026, 3, 29, 5, 45, tzinfo=HELSINKI)
    assert next_refresh(local, HELSINKI) == timedelta(minutes=15)


def test_clamp_is_correct_on_the_fall_back_day() -> None:
    local = datetime(2026, 10, 25, 5, 45, tzinfo=HELSINKI)
    assert next_refresh(local, HELSINKI) == timedelta(minutes=15)


# The two above pass against a DST-blind implementation too - nothing happens
# between 05:45 and 06:00 on either transition day. These pin the offset itself:
# both use the same UTC instant, and only the offset in force decides the band.
def test_the_band_uses_the_offset_in_force_after_the_spring_forward() -> None:
    """03:45 UTC is 06:45 EEST - it would read 05:45, and clamp, under EET."""
    now = datetime(2026, 3, 29, 3, 45, tzinfo=UTC)
    assert next_refresh(now, HELSINKI) == THREE_MIN


def test_the_clamp_uses_the_offset_in_force_after_the_fall_back() -> None:
    """03:45 UTC is 05:45 EET - it would read 06:45, and not clamp, under EEST."""
    now = datetime(2026, 10, 25, 3, 45, tzinfo=UTC)
    assert next_refresh(now, HELSINKI) == timedelta(minutes=15)


def test_never_returns_a_non_positive_duration() -> None:
    """Every minute of the day, all year, produces a usable sleep."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for offset in range(0, 366 * 24 * 60, 7):
        now = start + timedelta(minutes=offset)
        assert next_refresh(now, HELSINKI) >= MIN_INTERVAL
