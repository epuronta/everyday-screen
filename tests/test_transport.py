"""Tests for the Digitransit response parsing in app.transport."""

from datetime import UTC, datetime

import pytest

from app.transport import StopConfig, _parse_departures

# 2026-08-27 00:00 Helsinki (UTC+3 in August) as a Unix timestamp.
SERVICE_DAY = int(datetime(2026, 8, 26, 21, 0, tzinfo=UTC).timestamp())


def _stoptime(line: str, headsign: str, seconds_from_midnight: int) -> dict:
    return {
        "serviceDay": SERVICE_DAY,
        "realtimeDeparture": seconds_from_midnight,
        "realtime": True,
        "headsign": headsign,
        "trip": {"route": {"shortName": line}},
    }


def _stop_data(*stoptimes: dict, name: str = "Testikatu") -> dict:
    return {"name": name, "stoptimesWithoutPatterns": list(stoptimes)}


def test_parses_name_and_walk_time_from_the_config() -> None:
    result = _parse_departures(
        "H0062",
        _stop_data(name="Kotikatu"),
        StopConfig("H0062", walk_time_minutes=5),
    )
    assert result.stop_id == "H0062"
    assert result.stop_name == "Kotikatu"
    assert result.walk_time_minutes == 5
    assert result.departures == []


def test_departure_time_is_service_day_plus_seconds_from_midnight() -> None:
    result = _parse_departures(
        "H0062",
        _stop_data(_stoptime("561", "Leppävaara", 8 * 3600 + 15 * 60)),
        StopConfig("H0062"),
    )
    assert result.departures[0].time == datetime(2026, 8, 27, 5, 15, tzinfo=UTC)


def test_keeps_every_line_when_no_filter_is_configured() -> None:
    result = _parse_departures(
        "H0062",
        _stop_data(
            _stoptime("561", "Leppävaara", 100),
            _stoptime("999", "Muualle", 200),
        ),
        StopConfig("H0062"),
    )
    assert [d.line for d in result.departures] == ["561", "999"]


def test_drops_lines_outside_the_configured_set() -> None:
    result = _parse_departures(
        "H0062",
        _stop_data(
            _stoptime("561", "Leppävaara", 100),
            _stoptime("999", "Muualle", 200),
            _stoptime("54", "Keskusta", 300),
        ),
        StopConfig("H0062", lines={"561", "54"}),
    )
    assert [d.line for d in result.departures] == ["561", "54"]


def test_preserves_the_order_the_api_returned() -> None:
    result = _parse_departures(
        "H0062",
        _stop_data(
            _stoptime("561", "A", 300),
            _stoptime("561", "B", 100),
        ),
        StopConfig("H0062"),
    )
    assert [d.headsign for d in result.departures] == ["A", "B"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Leppävaara", "Leppävaara"),
        ("Leppävaara via Pitäjänmäki", "Leppävaara"),
        ("Rautatientori (M)", "Rautatientori"),
        ("Rautatientori(M)", "Rautatientori"),
        ("Rautatientori (M) via Kamppi", "Rautatientori"),
        # Only the first " via " splits, so later ones fall away with the rest.
        ("A via B via C", "A"),
    ],
)
def test_cleans_up_the_headsign(raw: str, expected: str) -> None:
    result = _parse_departures(
        "H0062", _stop_data(_stoptime("561", raw, 100)), StopConfig("H0062")
    )
    assert result.departures[0].headsign == expected


# FIXME: the " (M)" removesuffix in _parse_departures is unreachable - the
# preceding removesuffix("(M)") already strips the parenthesised part, leaving a
# trailing space that rstrip() handles. Harmless, but it reads as if it were
# doing something. Encoding the behaviour here so removing it stays safe.
def test_trailing_whitespace_is_stripped() -> None:
    result = _parse_departures(
        "H0062",
        _stop_data(_stoptime("561", "Leppävaara   ", 100)),
        StopConfig("H0062"),
    )
    assert result.departures[0].headsign == "Leppävaara"


def test_missing_stoptimes_key_yields_no_departures() -> None:
    result = _parse_departures("H0062", {"name": "Testikatu"}, StopConfig("H0062"))
    assert result.departures == []


def test_null_stoptimes_yields_no_departures() -> None:
    """The API returns null rather than [] for stops with nothing scheduled."""
    stop_data = {"name": "Testikatu", "stoptimesWithoutPatterns": None}
    result = _parse_departures("H0062", stop_data, StopConfig("H0062"))
    assert result.departures == []


# FIXME: a null headsign (which Digitransit does return for some trips) raises
# rather than degrading to a blank destination. One bad trip takes out the whole
# stop. Encoding current behaviour rather than fixing it here.
def test_null_headsign_raises() -> None:
    stop_data = _stop_data(_stoptime("561", "placeholder", 100))
    stop_data["stoptimesWithoutPatterns"][0]["headsign"] = None
    with pytest.raises(AttributeError):
        _parse_departures("H0062", stop_data, StopConfig("H0062"))
