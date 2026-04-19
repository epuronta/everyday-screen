import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from zoneinfo import ZoneInfo

import httpx

from . import settings

WFS_URL = "https://opendata.fmi.fi/wfs"
_TZ = ZoneInfo(settings.TIMEZONE)
CACHE_TTL = timedelta(minutes=10)

_OBS_QUERY = "fmi::observations::weather::timevaluepair"
_FCT_QUERY = "fmi::forecast::harmonie::surface::point::timevaluepair"


@dataclass
class CurrentWeather:
    temperature: float  # °C
    wind_speed: float  # m/s
    humidity: float  # %


# Lower value = worse condition (for worst-case outfit planning)
_ICON_PRIORITY: dict[str, int] = {
    "thunder": 0,
    "snow-3": 1,
    "snow-2": 2,
    "snow-1": 3,
    "sleet": 4,
    "rain-3": 5,
    "rain-2": 6,
    "rain-1": 7,
    "fog": 8,
    "cloudy": 9,
    "partly-cloudy": 10,
    "clear": 11,
}


class WeatherSymbol(IntEnum):
    """WeatherSymbol3 codes (FMI)."""

    CLEAR = 1
    PARTLY_CLOUDY = 2
    CLOUDY = 3
    RAIN_LIGHT = 21
    RAIN_MODERATE = 22
    RAIN_HEAVY = 23
    RAIN_SHOWER_LIGHT = 31
    RAIN_SHOWER_MODERATE = 32
    RAIN_SHOWER_HEAVY = 33
    SNOW_LIGHT = 41
    SNOW_MODERATE = 42
    SNOW_HEAVY = 43
    SNOW_SHOWER_LIGHT = 51
    SNOW_SHOWER_MODERATE = 52
    SNOW_SHOWER_HEAVY = 53
    THUNDER_LIGHT = 61
    THUNDER_MODERATE = 62
    THUNDER_HEAVY = 63
    THUNDER_SHOWER = 64
    SLEET_LIGHT = 71
    SLEET_MODERATE = 72
    SLEET_HEAVY = 73
    SLEET_SHOWER_LIGHT = 81
    SLEET_SHOWER_MODERATE = 82
    SLEET_SHOWER_HEAVY = 83
    FOG = 91
    FREEZING_FOG = 92


_SYMBOL_ICONS: dict[int, str] = {
    WeatherSymbol.CLEAR: "clear",
    WeatherSymbol.PARTLY_CLOUDY: "partly-cloudy",
    WeatherSymbol.CLOUDY: "cloudy",
    WeatherSymbol.RAIN_LIGHT: "rain-1",
    WeatherSymbol.RAIN_MODERATE: "rain-2",
    WeatherSymbol.RAIN_HEAVY: "rain-3",
    WeatherSymbol.RAIN_SHOWER_LIGHT: "rain-1",
    WeatherSymbol.RAIN_SHOWER_MODERATE: "rain-2",
    WeatherSymbol.RAIN_SHOWER_HEAVY: "rain-3",
    WeatherSymbol.SNOW_LIGHT: "snow-1",
    WeatherSymbol.SNOW_MODERATE: "snow-2",
    WeatherSymbol.SNOW_HEAVY: "snow-3",
    WeatherSymbol.SNOW_SHOWER_LIGHT: "snow-1",
    WeatherSymbol.SNOW_SHOWER_MODERATE: "snow-2",
    WeatherSymbol.SNOW_SHOWER_HEAVY: "snow-3",
    **dict.fromkeys(
        [
            WeatherSymbol.THUNDER_LIGHT,
            WeatherSymbol.THUNDER_MODERATE,
            WeatherSymbol.THUNDER_HEAVY,
            WeatherSymbol.THUNDER_SHOWER,
        ],
        "thunder",
    ),
    **dict.fromkeys(
        [
            WeatherSymbol.SLEET_LIGHT,
            WeatherSymbol.SLEET_MODERATE,
            WeatherSymbol.SLEET_HEAVY,
            WeatherSymbol.SLEET_SHOWER_LIGHT,
            WeatherSymbol.SLEET_SHOWER_MODERATE,
            WeatherSymbol.SLEET_SHOWER_HEAVY,
        ],
        "sleet",
    ),
    **dict.fromkeys([WeatherSymbol.FOG, WeatherSymbol.FREEZING_FOG], "fog"),
}


def _symbol_to_icon(code: int) -> str:
    return _SYMBOL_ICONS.get(code, "cloudy")


@dataclass
class ForecastHour:
    time: datetime
    temperature: float  # °C
    wind_speed: float  # m/s
    symbol: WeatherSymbol
    precipitation: float = 0.0  # mm
    icon: str = field(init=False)

    def __post_init__(self) -> None:
        self.icon = _symbol_to_icon(self.symbol)


@dataclass
class WeatherBlock:
    label: str  # "Aamu" / "Ilta"
    temp_min: float  # °C
    temp_max: float  # °C
    icon: str  # worst-case condition in the block


@dataclass
class WeatherDay:
    label: str  # "Tänään" / "Huomenna"
    blocks: list[WeatherBlock]


def _worst_icon(hours: list[ForecastHour]) -> str:
    if not hours:
        return "cloudy"
    return min(hours, key=lambda h: _ICON_PRIORITY.get(h.icon, 5)).icon


@dataclass
class WeatherData:
    current: CurrentWeather
    forecast: list[ForecastHour]

    @property
    def current_icon(self) -> str:
        return self.forecast[0].icon if self.forecast else "cloudy"

    def day_groups(self, tz: ZoneInfo, now: datetime) -> list[WeatherDay]:
        local_now = now.astimezone(tz)
        today = local_now.date()
        tomorrow = today + timedelta(days=1)

        def _block(
            date: object, start_h: int, end_h: int, label: str
        ) -> WeatherBlock | None:
            in_range = [
                f
                for f in self.forecast
                if f.time.astimezone(tz).date() == date
                and start_h <= f.time.astimezone(tz).hour < end_h
            ]
            if not in_range:
                return None
            icon = _worst_icon(in_range)
            temps = [f.temperature for f in in_range]
            return WeatherBlock(
                label=label, temp_min=min(temps), temp_max=max(temps), icon=icon
            )

        days = []
        for date, label in [(today, "Tänään"), (tomorrow, "Huomenna")]:
            blocks = [
                b
                for b in [_block(date, 6, 12, "Aamu"), _block(date, 12, 20, "Ilta")]
                if b is not None
            ]
            if blocks:
                days.append(WeatherDay(label=label, blocks=blocks))
        return days


@dataclass
class _Cache:
    data: WeatherData | None = None
    time: datetime | None = field(default=None)

    def is_fresh(self, now: datetime) -> bool:
        if self.data is None or self.time is None:
            return False
        return now - self.time < CACHE_TTL


_cache = _Cache()


def _parse_timeseries(xml_text: str) -> dict[str, list[tuple[datetime, float]]]:
    """Parse WFS timevaluepair XML into {param: [(time, value), ...]}."""
    root = ET.fromstring(xml_text)  # noqa: S314
    result = {}

    for ts in root.iter("{http://www.opengis.net/waterml/2.0}MeasurementTimeseries"):
        gml_id = ts.get("{http://www.opengis.net/gml/3.2}id", "")
        param = gml_id.rsplit("-", 1)[-1]

        points = []
        for tvp in ts.iter("{http://www.opengis.net/waterml/2.0}MeasurementTVP"):
            time_el = tvp.find("{http://www.opengis.net/waterml/2.0}time")
            value_el = tvp.find("{http://www.opengis.net/waterml/2.0}value")
            if (
                time_el is not None
                and time_el.text is not None
                and value_el is not None
                and value_el.text not in (None, "NaN")
            ):
                t = datetime.fromisoformat(time_el.text)
                points.append((t, float(value_el.text)))

        if points:
            result[param] = points

    return result


async def get_weather(place: str) -> WeatherData:
    now = datetime.now(tz=UTC)

    if _cache.is_fresh(now):
        return _cache.data  # type: ignore[return-value]

    end_of_day = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59)

    async with httpx.AsyncClient() as client:
        obs_resp = await client.get(
            WFS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "storedquery_id": _OBS_QUERY,
                "place": place,
                "timestep": "60",
                "parameters": "t2m,ws_10min,rh",
            },
        )
        obs_resp.raise_for_status()

        start_of_today = (
            now.astimezone(_TZ).replace(hour=0, minute=0, second=0).astimezone(UTC)
        )
        fct_resp = await client.get(
            WFS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "storedquery_id": _FCT_QUERY,
                "place": place,
                "starttime": start_of_today.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endtime": end_of_day.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timestep": "60",
                "parameters": "Temperature,WindSpeedMS,WeatherSymbol3,Precipitation1h",
            },
        )
        fct_resp.raise_for_status()

    obs = _parse_timeseries(obs_resp.text)
    fct = _parse_timeseries(fct_resp.text)

    current = CurrentWeather(
        temperature=obs["t2m"][-1][1],
        wind_speed=obs["ws_10min"][-1][1],
        humidity=obs["rh"][-1][1],
    )

    temps = dict(fct.get("Temperature", []))
    winds = dict(fct.get("WindSpeedMS", []))
    symbols = dict(fct.get("WeatherSymbol3", []))
    precips = dict(fct.get("Precipitation1h", []))

    forecast = [
        ForecastHour(
            time=t,
            temperature=v,
            wind_speed=winds[t],
            symbol=WeatherSymbol(int(symbols[t])),
            precipitation=precips.get(t, 0.0),
        )
        for t, v in sorted(temps.items())
        if t in winds and t in symbols
    ]

    _cache.data = WeatherData(current=current, forecast=forecast)
    _cache.time = now

    return _cache.data
