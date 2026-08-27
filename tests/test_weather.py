"""Tests for the FMI parsing and forecast aggregation in app.weather."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.weather import (
    CurrentWeather,
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
    day: date = TODAY,
) -> ForecastHour:
    return ForecastHour(
        time=datetime(day.year, day.month, day.day, hour, tzinfo=HELSINKI),
        temperature=temp,
        wind_speed=wind,
        symbol=symbol,
        precipitation=precip,
    )


def _data(*hours: ForecastHour) -> WeatherData:
    return WeatherData(
        current=CurrentWeather(temperature=15.0, wind_speed=2.0, humidity=60.0),
        forecast=list(hours),
    )


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
        label="Aamu", temp_min=10, temp_max=15, icon="clear", wind_speed_max=wind
    )
    assert block.wind_level == level


def test_current_icon_comes_from_the_first_forecast_hour() -> None:
    data = _data(_hour(9, symbol=WeatherSymbol.SNOW_HEAVY), _hour(10))
    assert data.current_icon == "snow-3"


def test_current_icon_without_a_forecast_is_cloudy() -> None:
    assert _data().current_icon == "cloudy"


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
    assert (aamu.label, aamu.temp_min, aamu.temp_max) == ("Aamu", 10.0, 14.0)
    assert aamu.wind_speed_max == 5.0
    assert (ilta.label, ilta.temp_min, ilta.temp_max) == ("Ilta", 16.0, 18.0)
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
