"""Tests for the spot-price maths and sparkline geometry in app.electricity."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.electricity import (
    CHEAP_THRESHOLD,
    EXPENSIVE_THRESHOLD,
    ElectricityData,
    SpotPrice,
    _catmull_rom_path,
)

HELSINKI = ZoneInfo("Europe/Helsinki")
# Mid-August: comfortably clear of both DST transitions.
MIDNIGHT = datetime(2026, 8, 27, 0, 0, tzinfo=HELSINKI)


def _hours(prices: list[float], start: datetime = MIDNIGHT) -> ElectricityData:
    return ElectricityData(
        hours=[
            SpotPrice(time=start + timedelta(hours=i), price=p)
            for i, p in enumerate(prices)
        ]
    )


def test_catmull_rom_starts_with_a_moveto() -> None:
    assert _catmull_rom_path([(0.0, 1.0)]) == "M 0.0,1.0"


def test_catmull_rom_emits_one_curve_per_segment() -> None:
    path = _catmull_rom_path([(0.0, 0.0), (10.0, 10.0), (20.0, 0.0)])
    assert path.startswith("M 0.0,0.0")
    assert path.count("C ") == 2
    assert path.endswith("20.0,0.0")


# FIXME: _catmull_rom_path indexes pts[0] before checking the length, so an empty
# list raises. Only safe today because sparkline() returns early on no data.
def test_catmull_rom_raises_on_an_empty_point_list() -> None:
    with pytest.raises(IndexError):
        _catmull_rom_path([])


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (-2.0, "cheap"),
        (0.0, "cheap"),
        (CHEAP_THRESHOLD, "cheap"),
        (CHEAP_THRESHOLD + 0.01, "ok"),
        (10.0, "ok"),
        (EXPENSIVE_THRESHOLD - 0.01, "ok"),
        (EXPENSIVE_THRESHOLD, "expensive"),
        (99.0, "expensive"),
    ],
)
def test_classify_bands(price: float, expected: str) -> None:
    """Both thresholds are inclusive - they classify as cheap/expensive, not ok."""
    assert ElectricityData(hours=[]).classify(price) == expected


def test_current_returns_the_price_for_the_current_hour() -> None:
    data = _hours([1.0, 2.0, 3.0])
    now = MIDNIGHT + timedelta(hours=1, minutes=37)
    current = data.current(now, HELSINKI)
    assert current is not None
    assert current.price == 2.0


def test_current_returns_none_when_the_hour_is_missing() -> None:
    data = _hours([1.0, 2.0])
    assert data.current(MIDNIGHT + timedelta(hours=9), HELSINKI) is None


def test_current_returns_none_without_data() -> None:
    assert ElectricityData(hours=[]).current(MIDNIGHT, HELSINKI) is None


def test_current_matches_across_timezone_representations() -> None:
    """Prices arrive UTC-tagged from the API; matching is done in local time."""
    utc_hours = ElectricityData(
        hours=[SpotPrice(time=MIDNIGHT.astimezone(ZoneInfo("UTC")), price=7.0)]
    )
    current = utc_hours.current(MIDNIGHT + timedelta(minutes=30), HELSINKI)
    assert current is not None
    assert current.price == 7.0


def test_sparkline_is_empty_without_data() -> None:
    assert ElectricityData(hours=[]).sparkline(MIDNIGHT, HELSINKI) == {}


def test_sparkline_is_empty_when_all_data_is_in_the_past() -> None:
    stale = _hours([1.0, 2.0], start=MIDNIGHT - timedelta(days=2))
    assert stale.sparkline(MIDNIGHT, HELSINKI) == {}


def test_sparkline_spans_a_fixed_48h_window() -> None:
    """Today occupies the left half regardless of how much data exists."""
    one_day = _hours([5.0] * 24).sparkline(MIDNIGHT, HELSINKI)
    two_days = _hours([5.0] * 48).sparkline(MIDNIGHT, HELSINKI)
    assert one_day["dividers"] == two_days["dividers"]
    assert one_day["width"] == two_days["width"] == 320
    assert one_day["pad_left"] == two_days["pad_left"] == 30


def test_sparkline_dividers_cover_every_second_hour() -> None:
    spark = _hours([5.0] * 48).sparkline(MIDNIGHT, HELSINKI)
    dividers = spark["dividers"]
    assert len(dividers) == 24
    assert [d["label"] for d in dividers[:3]] == ["0", "2", "4"]
    assert dividers[0]["x"] == spark["pad_left"]
    # x increases monotonically across the window
    assert [d["x"] for d in dividers] == sorted(d["x"] for d in dividers)


def test_sparkline_marks_exactly_one_day_boundary() -> None:
    spark = _hours([5.0] * 48).sparkline(MIDNIGHT, HELSINKI)
    boundaries = [d for d in spark["dividers"] if d["day_boundary"]]
    assert len(boundaries) == 1
    assert boundaries[0]["label"] == "0"


def test_sparkline_thresholds_step_in_tens_up_to_the_rounded_max() -> None:
    spark = _hours([3.0, 12.0, 7.0]).sparkline(MIDNIGHT, HELSINKI)
    assert [t["label"] for t in spark["thresholds"]] == ["0", "10", "20"]


def test_sparkline_uses_a_minimum_scale_of_ten_cents() -> None:
    """Flat cheap days would otherwise divide by zero."""
    spark = _hours([0.0] * 24).sparkline(MIDNIGHT, HELSINKI)
    assert [t["label"] for t in spark["thresholds"]] == ["0", "10"]


def test_sparkline_marks_the_current_hour() -> None:
    now = MIDNIGHT + timedelta(hours=3, minutes=20)
    spark = _hours([5.0] * 24).sparkline(now, HELSINKI)
    assert spark["current_x"] is not None
    assert spark["current_y"] is not None


def test_sparkline_has_no_current_marker_when_the_hour_is_absent() -> None:
    """Tomorrow-only data still renders, just without the now line."""
    tomorrow = _hours([5.0] * 24, start=MIDNIGHT + timedelta(days=1))
    spark = tomorrow.sparkline(MIDNIGHT, HELSINKI)
    assert spark["current_x"] is None
    assert spark["current_y"] is None


# FIXME: y_max is `ceil(max/10)*10 or 10`, which goes negative once the day's peak
# is below -10 c/kWh. price_to_y then divides by a negative scale, and
# range(0, y_max + 1, 10) yields nothing at all, so the y-axis labels disappear
# and the curve renders against an inverted scale. Deeply negative spot prices
# are rare but real in the Nordic market.
def test_sparkline_scale_breaks_on_deeply_negative_prices() -> None:
    spark = _hours([-12.0] * 24).sparkline(MIDNIGHT, HELSINKI)
    assert spark["thresholds"] == []
