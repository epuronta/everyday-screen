import asyncio
import logging
import math
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from . import renderer, settings
from .calendar import get_calendar, prepare_display
from .electricity import get_electricity
from .menu import Dish, MenuDay
from .menu_amica import get_amica_menu
from .menu_aromi import get_menu as get_aromi_menu
from .refresh import MAX_INTERVAL, MIN_INTERVAL, next_refresh
from .renderer import HEIGHT, WIDTH, render
from .transport import DEPARTURE_CAP, DEPARTURE_LOOKAHEAD, get_transport
from .weather import get_weather
from .weather_mock import mock_weather

log = logging.getLogger(__name__)

_FI_WEEKDAYS = [
    "maanantai",
    "tiistai",
    "keskiviikko",
    "torstai",
    "perjantai",
    "lauantai",
    "sunnuntai",
]
_FI_MONTHS = [
    "tammikuu",
    "helmikuu",
    "maaliskuu",
    "huhtikuu",
    "toukokuu",
    "kesäkuu",
    "heinäkuu",
    "elokuu",
    "syyskuu",
    "lokakuu",
    "marraskuu",
    "joulukuu",
]


def _fi_date(dt: datetime) -> str:
    month = _FI_MONTHS[dt.month - 1]
    return f"{_FI_WEEKDAYS[dt.weekday()].capitalize()} {dt.day}.{dt.month}. ({month})"


# Matches the range the firmware used when it drew this itself. The reading is
# known to be pessimistic - a full battery reports well under 100% - so the
# voltage is shown alongside the percentage rather than instead of it, which is
# what makes recalibrating this possible later.
_BATTERY_MIN_V = 3.0
_BATTERY_MAX_V = 4.2


def _battery_label(voltage: float | None) -> str:
    # A nan/inf reading would blow up on round() further down and take the whole
    # image with it. Dropping the label degrades to the pre-battery footer.
    if voltage is None or not math.isfinite(voltage):
        return ""
    if voltage <= _BATTERY_MIN_V:
        return "USB"
    ratio = (voltage - _BATTERY_MIN_V) / (_BATTERY_MAX_V - _BATTERY_MIN_V)
    percent = min(100, max(0, round(ratio * 100)))
    return f"{voltage:.2f} V ({percent} %)"


_SECONDS_PER_MINUTE = 60


def _interval_label(seconds: int) -> str:
    if seconds < _SECONDS_PER_MINUTE:
        return f"{seconds} s"
    return f"{round(seconds / _SECONDS_PER_MINUTE)} min"


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    _warn_on_clamped_override()
    await renderer.startup()
    yield
    await renderer.shutdown()


app = FastAPI(lifespan=_lifespan)


def _require_token(token: Annotated[str, Query()] = "") -> None:
    if settings.API_TOKEN and token != settings.API_TOKEN:
        raise HTTPException(status_code=403)


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
IMAGE_CACHE_TTL = timedelta(minutes=1)


@dataclass
class _CacheEntry:
    data: bytes
    time: datetime

    def is_fresh(self, now: datetime) -> bool:
        return now - self.time < IMAGE_CACHE_TTL


# (width, height, reported voltage, refresh seconds) - everything the rendered
# image varies with. Kept in step with the key built in _render_display.
_CacheKey = tuple[int, int, float | None, int]

_image_cache: dict[_CacheKey, _CacheEntry] = {}


TZ = ZoneInfo(settings.TIMEZONE)


async def _empty() -> list:
    return []


def _today_dishes(days: list[MenuDay] | None, today: date) -> list[Dish] | None:
    if not days:
        return None
    for day in days:
        if day.date == today:
            return day.dishes or None
    return None


def _build_context(  # noqa: PLR0913
    now: datetime,
    weather: object,
    electricity: object,
    transport: object,
    calendar: object,
    menu_amica: list[MenuDay] | None,
    menu_aromi: list[MenuDay] | None,
    width: int,
    height: int,
    refresh_label: str,
    battery_label: str,
) -> dict:
    local = now.astimezone(TZ)
    today = local.date()
    menus = []
    if dishes := _today_dishes(menu_aromi, today):
        menus.append({"label": settings.AROMI_LABEL, "dishes": dishes})
    if dishes := _today_dishes(menu_amica, today):
        menus.append({"label": settings.AMICA_LABEL, "dishes": dishes})
    return {
        "time": local.strftime("%H:%M"),
        "date": _fi_date(local),
        "weather": weather,
        "electricity": electricity,
        "transport": transport,
        "calendar": prepare_display(calendar, now, TZ, _FI_WEEKDAYS)
        if calendar
        else [],
        "menus": menus,
        "now": now,
        "tz": TZ,
        "timedelta": timedelta,
        "departure_cap": DEPARTURE_CAP,
        "departure_lookahead": DEPARTURE_LOOKAHEAD,
        "width": width,
        "height": height,
        "refresh_label": refresh_label,
        "battery_label": battery_label,
    }


async def _fetch_aromi() -> list[MenuDay] | None:
    if not (
        settings.AROMI_URL
        and settings.AROMI_RESTAURANT_ID
        and settings.AROMI_DINER_GROUP_ID
    ):
        return None
    return await get_aromi_menu(
        settings.AROMI_URL,
        settings.AROMI_RESTAURANT_ID,
        settings.AROMI_DINER_GROUP_ID,
    )


async def _fetch_data(now: datetime, *, use_mock_weather: bool = False) -> tuple:
    results = await asyncio.gather(
        mock_weather(now, TZ) if use_mock_weather else get_weather(settings.FMI_CITY),
        get_electricity(),
        get_transport(settings.DIGITRANSIT_API_KEY, settings.HSL_STOPS),
        get_calendar(settings.GCAL_ICAL_URL) if settings.GCAL_ICAL_URL else _empty(),
        get_amica_menu(settings.AMICA_URL) if settings.AMICA_URL else _empty(),
        _fetch_aromi(),
        return_exceptions=True,
    )
    names = (
        "weather",
        "electricity",
        "transport",
        "calendar",
        "menu_amica",
        "menu_aromi",
    )
    out = []
    for name, result in zip(names, results, strict=True):
        if isinstance(result, Exception):
            log.error("Failed to fetch %s", name, exc_info=result)
            out.append(None)
        else:
            out.append(result)
    return tuple(out)


@app.get("/")
async def read_display(
    request: Request,
    width: Annotated[int, Query()] = WIDTH,
    height: Annotated[int, Query()] = HEIGHT,
    use_mock_weather: Annotated[bool, Query(alias="mock_weather")] = False,  # noqa: FBT002
    battery: Annotated[float | None, Query()] = None,
    _: Annotated[None, Depends(_require_token)] = None,
):
    now = datetime.now(tz=UTC)
    fetched = await _fetch_data(now, use_mock_weather=use_mock_weather)
    weather, electricity, transport, calendar, menu_amica, menu_aromi = fetched
    return templates.TemplateResponse(
        request,
        "display.html",
        _build_context(
            now,
            weather,
            electricity,
            transport,
            calendar,
            menu_amica,
            menu_aromi,
            width,
            height,
            _interval_label(_next_refresh_seconds(now)),
            _battery_label(battery),
        ),
    )


_MIN_SECONDS = int(MIN_INTERVAL.total_seconds())
_MAX_SECONDS = int(MAX_INTERVAL.total_seconds())


def _clamp_interval(seconds: int) -> int:
    return min(max(seconds, _MIN_SECONDS), _MAX_SECONDS)


def _warn_on_clamped_override() -> None:
    configured = settings.REFRESH_OVERRIDE_SECONDS
    if configured and configured != _clamp_interval(configured):
        log.warning(
            "REFRESH_OVERRIDE_SECONDS=%ss is outside the %ss-%ss the device "
            "accepts; serving %ss instead",
            configured,
            _MIN_SECONDS,
            _MAX_SECONDS,
            _clamp_interval(configured),
        )


def _next_refresh_seconds(now: datetime) -> int:
    """How long the device should sleep, as the device is told it.

    The override exists so a dev instance can be iterated on without waiting
    out a 10-minute band. Prod leaves it at 0.

    It is clamped to the window the firmware will actually honour. Handing out
    30s would get rejected on the device and fall back to a 15-minute retry,
    making a dev instance slower rather than faster - while the footer happily
    rendered the 30s that never happened.
    """
    if settings.REFRESH_OVERRIDE_SECONDS:
        return _clamp_interval(settings.REFRESH_OVERRIDE_SECONDS)
    return int(next_refresh(now, TZ).total_seconds())


async def _render_display(
    width: int, height: int, battery: float | None = None
) -> Response:
    now = datetime.now(tz=UTC)

    # Computed per request, never cached alongside the image - a cached image
    # served late in a band must still hand out a current interval.
    seconds = _next_refresh_seconds(now)
    headers = {"X-Next-Refresh": str(seconds)}

    # Both the interval and the voltage are rendered into the image, so they
    # have to be part of its identity or a hit serves someone else's numbers.
    cache_key = (width, height, battery, seconds)
    entry = _image_cache.get(cache_key)

    if entry and entry.is_fresh(now):
        return Response(content=entry.data, media_type="image/png", headers=headers)

    fetched = await _fetch_data(now)
    weather, electricity, transport, calendar, menu_amica, menu_aromi = fetched
    ctx = _build_context(
        now,
        weather,
        electricity,
        transport,
        calendar,
        menu_amica,
        menu_aromi,
        width,
        height,
        _interval_label(seconds),
        _battery_label(battery),
    )
    html = templates.env.get_template("display.html").render(ctx)
    image = await render(html, width, height)

    # The key now varies with the reported voltage, so entries would otherwise
    # accumulate one per distinct reading and never be reclaimed.
    for stale in [k for k, v in _image_cache.items() if not v.is_fresh(now)]:
        del _image_cache[stale]
    _image_cache[cache_key] = _CacheEntry(data=image, time=now)

    return Response(content=image, media_type="image/png", headers=headers)


@app.get("/display.png")
async def get_display_png(
    width: Annotated[int, Query()] = WIDTH,
    height: Annotated[int, Query()] = HEIGHT,
    battery: Annotated[float | None, Query()] = None,
    _: Annotated[None, Depends(_require_token)] = None,
):
    return await _render_display(width, height, battery)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
