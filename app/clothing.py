"""What the kids should wear, from the forecast for the hours they are out.

Three independent choices, composed into one line:

- rain picks the outer layer and always brings the shell trousers with it
- felt temperature picks what goes underneath, and the jacket on dry days
- wet ground picks the shoes

Thresholds are written to be argued with. Every branch has a test, so moving
one tells you what it changed.
"""

import math

from .weather import OutdoorDay

_FREEZING = 0.0

_DEEP_WINTER = -10.0
_WINTER = 0.0
_COLD_SHOULDER = 7.0
_SHOULDER = 12.0
_COOL = 18.0
_WARM = 22.0

# Felt temperature bands, coldest first: the first band the day fits wins.
# (below this felt °C, what goes under the outer layer, hands and head)
_BANDS: list[tuple[float, str, str]] = [
    (
        _DEEP_WINTER,
        "villakerrasto ja välikerros",
        "paksut toppahanskat, kypärähattu ja pipo",
    ),
    (_WINTER, "villapaita", "lämpimät hanskat, pipo"),
    (_COLD_SHOULDER, "lämmin paita", "ohuet hanskat, pipo"),
    (_SHOULDER, "pitkähihainen", "pipo tai lippis"),
    (_COOL, "t-paita, verkkarit", "lippis"),
    (_WARM, "t-paita, shortsit tai ohuet housut", "lippis"),
    (math.inf, "t-paita, shortsit", "lippis"),
]

# Rubber boots are about standing water, so it takes both a wet day and a long
# one. A single afternoon downpour leaves the yard crossable in gore-tex.
_BOOTS_WET_HOURS = 5
_BOOTS_TOTAL_MM = 4.0


def _outer(feels_min: float, *, wet: bool) -> str:
    if feels_min < _DEEP_WINTER:
        return "Toppapuku"
    if feels_min < _WINTER:
        return "Toppatakki ja -housut"
    if wet:
        return "Kuoritakki ja -housut"
    if feels_min < _COOL:
        return "Kuoritakki"
    if feels_min < _WARM:
        return "Verkkatakki"
    return ""


def _shoes(day: OutdoorDay, *, wet: bool) -> str:
    # Melting underfoot beats any amount of gore-tex, and so does a yard that
    # has been rained on all day.
    thaws = day.air_min < _FREEZING < day.air_max
    soaked = (
        wet and day.wet_hours >= _BOOTS_WET_HOURS and day.rain_total >= _BOOTS_TOTAL_MM
    )
    if thaws or soaked:
        return "kumpparit"
    if day.feels_min < _WINTER:
        return "talvikengät"
    if wet or day.feels_min <= _SHOULDER:
        return "gore-kengät"
    if day.feels_min <= _WARM:
        return "lenkkarit"
    return "sandaalit tai lenkkarit"


def advice(day: OutdoorDay) -> str:
    """One line of what to put on, for a day nobody gets to re-dress for."""
    # Below freezing it falls as snow, which the winter layers already handle.
    wet = day.wet_hours > 0 and day.air_max > _FREEZING
    _, under, extras = next(b for b in _BANDS if day.feels_min < b[0])
    parts = [
        _outer(day.feels_min, wet=wet),
        under,
        extras,
        _shoes(day, wet=wet),
    ]
    line = ", ".join(p for p in parts if p)
    return line[0].upper() + line[1:] + "."
