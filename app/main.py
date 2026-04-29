import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from . import renderer, settings
from .calendar import get_calendar, prepare_display
from .electricity import get_electricity
from .renderer import HEIGHT, WIDTH, render
from .transport import get_transport
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


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None]:
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


_image_cache: dict[tuple[int, int, str], _CacheEntry] = {}


TZ = ZoneInfo(settings.TIMEZONE)


async def _empty() -> list:
    return []


def _build_context(  # noqa: PLR0913
    now: datetime,
    weather: object,
    electricity: object,
    transport: object,
    calendar: object,
    width: int,
    height: int,
) -> dict:
    local = now.astimezone(TZ)
    return {
        "time": local.strftime("%H:%M"),
        "date": _fi_date(local),
        "weather": weather,
        "electricity": electricity,
        "transport": transport,
        "calendar": prepare_display(calendar, now, TZ, _FI_WEEKDAYS)
        if calendar
        else [],
        "now": now,
        "tz": TZ,
        "timedelta": timedelta,
        "width": width,
        "height": height,
    }


async def _fetch_data(now: datetime, *, use_mock_weather: bool = False) -> tuple:
    results = await asyncio.gather(
        mock_weather(now, TZ) if use_mock_weather else get_weather(settings.FMI_CITY),
        get_electricity(),
        get_transport(settings.DIGITRANSIT_API_KEY, settings.HSL_STOPS),
        get_calendar(settings.GCAL_ICAL_URL) if settings.GCAL_ICAL_URL else _empty(),
        return_exceptions=True,
    )
    names = ("weather", "electricity", "transport", "calendar")
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
    _: Annotated[None, Depends(_require_token)] = None,
):
    now = datetime.now(tz=UTC)
    weather, electricity, transport, calendar = await _fetch_data(
        now, use_mock_weather=use_mock_weather
    )
    return templates.TemplateResponse(
        request,
        "display.html",
        _build_context(now, weather, electricity, transport, calendar, width, height),
    )


async def _render_display(width: int, height: int) -> Response:
    now = datetime.now(tz=UTC)
    cache_key = (width, height)
    entry = _image_cache.get(cache_key)

    if entry and entry.is_fresh(now):
        return Response(content=entry.data, media_type="image/png")

    weather, electricity, transport, calendar = await _fetch_data(now)
    ctx = _build_context(now, weather, electricity, transport, calendar, width, height)
    html = templates.env.get_template("display.html").render(ctx)
    image = await render(html, width, height)

    _image_cache[cache_key] = _CacheEntry(data=image, time=now)

    return Response(content=image, media_type="image/png")


@app.get("/display.png")
async def get_display_png(
    width: Annotated[int, Query()] = WIDTH,
    height: Annotated[int, Query()] = HEIGHT,
    _: Annotated[None, Depends(_require_token)] = None,
):
    return await _render_display(width, height)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
