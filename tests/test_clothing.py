"""One case per branch of the clothing rules.

The thresholds are expected to be tweaked, so these tests exist to say what a
tweak changed rather than to defend the current numbers.
"""

import pytest

from app.clothing import advice
from app.weather import OutdoorDay


def _day(
    *,
    feels_min: float,
    feels_max: float | None = None,
    air_min: float | None = None,
    air_max: float | None = None,
    rain_total: float = 0.0,
    wet_hours: int = 0,
) -> OutdoorDay:
    return OutdoorDay(
        label="Tänään",
        feels_min=feels_min,
        feels_max=feels_max if feels_max is not None else feels_min + 3.0,
        air_min=air_min if air_min is not None else feels_min + 2.0,
        air_max=air_max if air_max is not None else feels_min + 5.0,
        rain_total=rain_total,
        wet_hours=wet_hours,
    )


@pytest.mark.parametrize(
    ("feels_min", "expected"),
    [
        (-15.0, "Toppapuku, villakerrasto ja välikerros"),
        (-5.0, "Toppatakki ja -housut, villapaita"),
        (3.0, "Kuoritakki, lämmin paita"),
        (9.0, "Kuoritakki, pitkähihainen"),
        (15.0, "Kuoritakki, t-paita, verkkarit"),
        (20.0, "Verkkatakki, t-paita, shortsit tai ohuet housut"),
        (25.0, "T-paita, shortsit"),
    ],
)
def test_dry_day_layers_by_felt_temperature(feels_min: float, expected: str) -> None:
    assert advice(_day(feels_min=feels_min)).startswith(expected)


def test_rain_adds_the_shell_trousers() -> None:
    dry = advice(_day(feels_min=9.0))
    wet = advice(_day(feels_min=9.0, rain_total=1.0, wet_hours=2))
    assert dry.startswith("Kuoritakki,")
    assert wet.startswith("Kuoritakki ja -housut,")
    # What goes underneath is the temperature's business, not the rain's.
    assert "pitkähihainen" in dry
    assert "pitkähihainen" in wet


def test_rain_brings_the_shell_trousers_at_any_temperature() -> None:
    # Shell trousers over shorts on a warm wet day: rain outranks the heat.
    assert advice(_day(feels_min=25.0, rain_total=1.0, wet_hours=2)).startswith(
        "Kuoritakki ja -housut, t-paita, shortsit"
    )


def test_snow_is_left_to_the_winter_layers() -> None:
    # Precipitation below freezing is snow, so no shell and no gore-tex.
    snowy = _day(
        feels_min=-6.0, air_min=-8.0, air_max=-2.0, rain_total=6.0, wet_hours=6
    )
    line = advice(snowy)
    assert line.startswith("Toppatakki ja -housut")
    assert "kuori" not in line.lower()
    assert line.endswith("talvikengät.")


def test_a_long_wet_day_calls_for_rubber_boots() -> None:
    assert advice(_day(feels_min=8.0, rain_total=6.0, wet_hours=6)).endswith(
        "kumpparit."
    )


def test_one_downpour_is_not_enough_for_rubber_boots() -> None:
    assert advice(_day(feels_min=8.0, rain_total=8.0, wet_hours=2)).endswith(
        "gore-kengät."
    )


def test_all_day_drizzle_is_not_enough_either() -> None:
    assert advice(_day(feels_min=8.0, rain_total=2.4, wet_hours=6)).endswith(
        "gore-kengät."
    )


def test_a_thaw_calls_for_rubber_boots_even_without_rain() -> None:
    # Frost at eight, above zero by noon: the yard is slush by the time they
    # come home, whatever the sky does.
    assert advice(_day(feels_min=-3.0, air_min=-4.0, air_max=4.0)).endswith(
        "kumpparit."
    )


def test_a_dry_hot_day_ends_in_sandals() -> None:
    assert advice(_day(feels_min=24.0)).endswith("sandaalit tai lenkkarit.")


@pytest.mark.parametrize(
    ("feels_min", "shoes"),
    [
        (11.9, "gore-kengät."),
        # Inclusive on purpose: the jacket runs to 18, the gore-tex does not.
        (12.0, "gore-kengät."),
        (12.1, "lenkkarit."),
    ],
)
def test_gore_tex_ends_at_the_shoulder_threshold(feels_min: float, shoes: str) -> None:
    assert advice(_day(feels_min=feels_min)).endswith(shoes)


def test_the_line_reads_as_a_sentence() -> None:
    assert advice(_day(feels_min=9.0)) == (
        "Kuoritakki, pitkähihainen, pipo tai lippis, gore-kengät."
    )
