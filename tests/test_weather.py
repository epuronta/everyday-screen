"""Tests for the FMI parsing and forecast aggregation in app.weather."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.weather import (
    ForecastHour,
    WeatherBlock,
    WeatherData,
    WeatherSymbol,
    _parse_timeseries,
    _symbol_to_icon,
    _worst_icon,
)

HELSINKI = ZoneInfo("Europe/Helsinki")
TODAY = date(2026, 8, 27)
NOW = datetime(2026, 8, 27, 8, 0, tzinfo=HELSINKI)
FIXTURES = Path(__file__).parent / "fixtures"


def _hour(
    hour: int,
    *,
    temp: float = 15.0,
    wind: float = 2.0,
    symbol: WeatherSymbol = WeatherSymbol.CLEAR,
    precip: float = 0.0,
    feels: float | None = None,
    day: date = TODAY,
) -> ForecastHour:
    return ForecastHour(
        time=datetime(day.year, day.month, day.day, hour, tzinfo=HELSINKI),
        temperature=temp,
        wind_speed=wind,
        symbol=symbol,
        precipitation=precip,
        feels_like=feels,
    )


def _data(*hours: ForecastHour) -> WeatherData:
    return WeatherData(forecast=list(hours))


@pytest.mark.parametrize(
    ("symbol", "icon"),
    [
        (WeatherSymbol.CLEAR, "clear"),
        (WeatherSymbol.PARTLY_CLOUDY, "partly-cloudy"),
        (WeatherSymbol.RAIN_LIGHT, "rain-1"),
        (WeatherSymbol.RAIN_SHOWER_HEAVY, "rain-3"),
        (WeatherSymbol.SNOW_MODERATE, "snow-2"),
        (WeatherSymbol.THUNDER_SHOWER, "thunder"),
        (WeatherSymbol.SLEET_HEAVY, "sleet"),
        (WeatherSymbol.FREEZING_FOG, "fog"),
    ],
)
def test_symbol_to_icon(symbol: WeatherSymbol, icon: str) -> None:
    assert _symbol_to_icon(symbol) == icon


def test_unknown_symbol_falls_back_to_cloudy() -> None:
    assert _symbol_to_icon(999) == "cloudy"


def test_forecast_hour_derives_its_icon() -> None:
    assert _hour(9, symbol=WeatherSymbol.RAIN_HEAVY).icon == "rain-3"


def test_worst_icon_picks_the_worst_condition() -> None:
    """Worst-case wins so the display supports outfit planning."""
    hours = [
        _hour(9, symbol=WeatherSymbol.CLEAR),
        _hour(10, symbol=WeatherSymbol.RAIN_LIGHT),
        _hour(11, symbol=WeatherSymbol.THUNDER_LIGHT),
    ]
    assert _worst_icon(hours) == "thunder"


def test_worst_icon_of_nothing_is_cloudy() -> None:
    assert _worst_icon([]) == "cloudy"


@pytest.mark.parametrize(
    ("wind", "level"),
    [(0.0, 1), (3.9, 1), (4.0, 2), (7.9, 2), (8.0, 3), (20.0, 3)],
)
def test_wind_level_thresholds(wind: float, level: int) -> None:
    block = WeatherBlock(
        label="Aamu", feels_min=10, feels_max=15, icon="clear", wind_speed_max=wind
    )
    assert block.wind_level == level


def test_felt_temperature_falls_back_to_the_air_temperature() -> None:
    assert _hour(9, temp=3.0).felt == 3.0
    assert _hour(9, temp=3.0, feels=-1.4).felt == -1.4


def test_day_blocks_report_felt_temperatures_not_air() -> None:
    data = _data(
        _hour(7, temp=10.0, feels=6.0),
        _hour(11, temp=14.0, feels=11.5),
    )
    aamu = data.day_groups(HELSINKI, NOW)[0].blocks[0]
    assert (aamu.feels_min, aamu.feels_max) == (6.0, 11.5)


def test_day_groups_splits_morning_and_evening() -> None:
    data = _data(
        _hour(7, temp=10.0, wind=3.0),
        _hour(11, temp=14.0, wind=5.0),
        _hour(13, temp=18.0, wind=2.0),
        _hour(19, temp=16.0, wind=9.0),
    )
    days = data.day_groups(HELSINKI, NOW)
    assert [d.label for d in days] == ["Tänään"]
    aamu, ilta = days[0].blocks
    assert (aamu.label, aamu.feels_min, aamu.feels_max) == ("Aamu", 10.0, 14.0)
    assert aamu.wind_speed_max == 5.0
    assert (ilta.label, ilta.feels_min, ilta.feels_max) == ("Ilta", 16.0, 18.0)
    assert ilta.wind_level == 3


def test_day_groups_excludes_hours_outside_the_blocks() -> None:
    """Only 06:00-20:00 is shown; night hours are dropped."""
    data = _data(_hour(3), _hour(22))
    assert data.day_groups(HELSINKI, NOW) == []


def test_day_groups_keeps_an_empty_morning_slot_for_today() -> None:
    """Layout stays stable once the morning has passed with no data left."""
    data = _data(_hour(14, temp=18.0))
    days = data.day_groups(HELSINKI, NOW)
    aamu, ilta = days[0].blocks
    assert aamu.empty
    assert not ilta.empty


def test_day_groups_does_not_pad_tomorrow() -> None:
    tomorrow = TODAY + timedelta(days=1)
    data = _data(_hour(14, day=tomorrow))
    days = data.day_groups(HELSINKI, NOW)
    assert [d.label for d in days] == ["Huomenna"]
    assert [b.label for b in days[0].blocks] == ["Ilta"]


def test_day_groups_covers_today_and_tomorrow_only() -> None:
    data = _data(
        _hour(9),
        _hour(9, day=TODAY + timedelta(days=1)),
        _hour(9, day=TODAY + timedelta(days=2)),
    )
    days = data.day_groups(HELSINKI, NOW)
    assert [d.date for d in days] == [TODAY, TODAY + timedelta(days=1)]


def test_rain_chart_draws_one_box_per_millimetre() -> None:
    data = _data(_hour(9, precip=2.4))
    chart = data.rain_chart(TODAY, HELSINKI)
    # 2.4mm rounds up to 3 boxes
    assert len(chart["boxes"]) == 3


def test_rain_chart_caps_at_five_boxes() -> None:
    data = _data(_hour(9, precip=40.0))
    assert len(data.rain_chart(TODAY, HELSINKI)["boxes"]) == 5


def test_rain_chart_is_empty_on_a_dry_day() -> None:
    data = _data(_hour(9), _hour(10))
    chart = data.rain_chart(TODAY, HELSINKI)
    assert chart["boxes"] == []
    assert chart["labels"] == []


def test_rain_chart_labels_the_ends_of_each_wet_stretch() -> None:
    data = _data(
        _hour(9, precip=1.0),
        _hour(10, precip=1.0),
        _hour(11, precip=1.0),
        _hour(15, precip=1.0),
    )
    labels = [lbl["label"] for lbl in data.rain_chart(TODAY, HELSINKI)["labels"]]
    assert labels == ["9", "11", "15"]


def test_rain_chart_has_a_fixed_geometry() -> None:
    chart = _data(_hour(9, precip=1.0)).rain_chart(TODAY, HELSINKI)
    assert chart["y_max"] == 5
    assert chart["chart_h"] == 70
    assert chart["height"] == 84
    assert len(chart["grid_lines"]) == 23


def test_rain_chart_ignores_other_days() -> None:
    data = _data(_hour(9, precip=5.0, day=TODAY + timedelta(days=1)))
    assert data.rain_chart(TODAY, HELSINKI)["boxes"] == []


def test_parse_timeseries_keys_on_the_gml_id_suffix() -> None:
    xml_text = (FIXTURES / "fmi_timevaluepair.xml").read_text(encoding="utf-8")
    result = _parse_timeseries(xml_text)
    assert set(result) == {"temperature", "windspeedms"}


def test_parse_timeseries_drops_nan_readings() -> None:
    xml_text = (FIXTURES / "fmi_timevaluepair.xml").read_text(encoding="utf-8")
    result = _parse_timeseries(xml_text)
    assert result["temperature"] == [
        (datetime(2026, 8, 27, 6, 0, tzinfo=UTC), 15.3),
        (datetime(2026, 8, 27, 8, 0, tzinfo=UTC), 17.1),
    ]


def test_parse_timeseries_omits_series_with_no_usable_points() -> None:
    """An all-NaN series is absent rather than present-and-empty."""
    xml_text = (FIXTURES / "fmi_timevaluepair.xml").read_text(encoding="utf-8")
    assert "humidity" not in _parse_timeseries(xml_text)


TOMORROW = TODAY + timedelta(days=1)


@pytest.mark.parametrize(
    ("hour", "label", "target"),
    [
        (0, "Tänään", TODAY),
        (7, "Tänään", TODAY),
        (15, "Tänään", TODAY),
        (16, "Huomenna", TOMORROW),
        (23, "Huomenna", TOMORROW),
    ],
)
def test_the_outdoor_window_rolls_over_when_the_day_is_out_of_reach(
    hour: int, label: str, target: date
) -> None:
    # Marking the target day warmer is what proves which day got picked.
    data = _data(
        *(_hour(h, day=TODAY, feels=1.0) for h in range(24)),
        *(_hour(h, day=TOMORROW, feels=2.0) for h in range(24)),
    )
    now = datetime(TODAY.year, TODAY.month, TODAY.day, hour, tzinfo=HELSINKI)
    window = data.outdoor_day(HELSINKI, now)
    assert window is not None
    assert window.label == label
    assert window.feels_min == (1.0 if target == TODAY else 2.0)


def test_the_window_covers_eight_to_four_only() -> None:
    data = _data(
        _hour(7, feels=-40.0),  # before they leave
        _hour(8, feels=1.0),
        _hour(15, feels=5.0),
        _hour(16, feels=40.0),  # after they are home
    )
    window = data.outdoor_day(HELSINKI, NOW)
    assert window is not None
    assert (window.feels_min, window.feels_max) == (1.0, 5.0)


def test_the_window_keeps_air_and_felt_temperatures_apart() -> None:
    data = _data(_hour(9, temp=1.0, feels=-4.0), _hour(12, temp=6.0, feels=2.0))
    window = data.outdoor_day(HELSINKI, NOW)
    assert window is not None
    assert (window.feels_min, window.feels_max) == (-4.0, 2.0)
    assert (window.air_min, window.air_max) == (1.0, 6.0)


def test_only_hours_with_measurable_rain_count_as_wet() -> None:
    data = _data(
        _hour(9, precip=0.0),
        _hour(10, precip=0.05),  # a rounding artefact, not weather
        _hour(11, precip=0.1),
        _hour(12, precip=2.4),
    )
    window = data.outdoor_day(HELSINKI, NOW)
    assert window is not None
    assert window.wet_hours == 2
    assert window.rain_total == pytest.approx(2.55)


def test_no_forecast_for_the_window_means_no_advice() -> None:
    assert _data(_hour(7), _hour(17)).outdoor_day(HELSINKI, NOW) is None
