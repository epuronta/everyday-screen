# ruff: noqa: S311 — mock data, not crypto
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .weather import CurrentWeather, ForecastHour, WeatherData

_RAIN_CHANCE = 0.2
_HEAVY_RAIN = 4.0
_MODERATE_RAIN = 2.0


async def mock_weather(now: datetime, tz: ZoneInfo) -> WeatherData:
    today = now.astimezone(tz).replace(minute=0, second=0, microsecond=0)
    precip = [
        round(random.uniform(0, 5), 1) if random.random() < _RAIN_CHANCE else 0.0
        for _ in range(48)
    ]
    day_base = [
        random.uniform(-20, 20) for _ in range(2)
    ]  # base per day, leaving room for +10
    forecast = []
    for h in range(48):
        temp = round(day_base[h // 24] + random.uniform(0, 10), 1)
        if precip[h] == 0:
            symbol = 2
        elif temp < 0:
            symbol = (
                41
                if precip[h] < _MODERATE_RAIN
                else 42
                if precip[h] < _HEAVY_RAIN
                else 43
            )
        elif -3 <= temp <= 3:  # noqa: PLR2004
            symbol = 71  # sleet
        elif precip[h] < _MODERATE_RAIN:
            symbol = 21
        elif precip[h] < _HEAVY_RAIN:
            symbol = 22
        else:
            symbol = 23
        forecast.append(
            ForecastHour(
                time=today.replace(hour=h % 24) + timedelta(days=h // 24),
                temperature=temp,
                wind_speed=3.0,
                symbol=symbol,
                precipitation=precip[h],
            )
        )
    return WeatherData(
        current=CurrentWeather(
            temperature=forecast[0].temperature, wind_speed=3.0, humidity=80.0
        ),
        forecast=forecast,
    )
