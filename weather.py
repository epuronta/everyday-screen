import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

WFS_URL = "https://opendata.fmi.fi/wfs"
CACHE_TTL = timedelta(minutes=10)

_OBS_QUERY = "fmi::observations::weather::timevaluepair"
_FCT_QUERY = "fmi::forecast::harmonie::surface::point::timevaluepair"


@dataclass
class CurrentWeather:
    temperature: float  # °C
    wind_speed: float  # m/s
    humidity: float  # %


_SYMBOL_ICONS: dict[int, str] = {
    1: "clear",
    2: "partly-cloudy",
    3: "cloudy",
    **dict.fromkeys([21, 22, 23, 31, 32, 33], "rain"),
    **dict.fromkeys([41, 42, 43, 51, 52, 53], "snow"),
    **dict.fromkeys([61, 62, 63, 64], "thunder"),
    **dict.fromkeys([71, 72, 73, 81, 82, 83], "sleet"),
    **dict.fromkeys([91, 92], "fog"),
}


def _symbol_to_icon(code: int) -> str:
    return _SYMBOL_ICONS.get(code, "cloudy")


@dataclass
class ForecastHour:
    time: datetime
    temperature: float  # °C
    wind_speed: float  # m/s
    symbol: int  # WeatherSymbol3 code
    icon: str = field(init=False)

    def __post_init__(self) -> None:
        self.icon = _symbol_to_icon(self.symbol)


@dataclass
class WeatherData:
    current: CurrentWeather
    forecast: list[ForecastHour]

    @property
    def current_icon(self) -> str:
        return self.forecast[0].icon if self.forecast else "cloudy"


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

    end_of_day = now.replace(hour=23, minute=59, second=59)

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

        fct_resp = await client.get(
            WFS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "storedquery_id": _FCT_QUERY,
                "place": place,
                "starttime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endtime": end_of_day.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timestep": "60",
                "parameters": "Temperature,WindSpeedMS,WeatherSymbol3",
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

    forecast = [
        ForecastHour(time=t, temperature=v, wind_speed=winds[t], symbol=int(symbols[t]))
        for t, v in sorted(temps.items())
        if t in winds and t in symbols
    ]

    _cache.data = WeatherData(current=current, forecast=forecast)
    _cache.time = now

    return _cache.data
