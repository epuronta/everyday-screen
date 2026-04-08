import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from . import settings
from .electricity import get_electricity
from .renderer import HEIGHT, WIDTH, render
from .transport import get_transport
from .weather import get_weather

log = logging.getLogger(__name__)

app = FastAPI()


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


def _build_context(  # noqa: PLR0913
    now: datetime,
    weather: object,
    electricity: object,
    transport: object,
    width: int,
    height: int,
) -> dict:
    return {
        "time": now.astimezone().strftime("%H:%M"),
        "date": now.astimezone().strftime("%A, %b %d"),
        "weather": weather,
        "electricity": electricity,
        "transport": transport,
        "now": now,
        "width": width,
        "height": height,
    }


async def _fetch_data() -> tuple:
    results = await asyncio.gather(
        get_weather(settings.FMI_CITY),
        get_electricity(),
        get_transport(
            settings.DIGITRANSIT_API_KEY, settings.HSL_STOPS, settings.HSL_LINES
        ),
        return_exceptions=True,
    )
    names = ("weather", "electricity", "transport")
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
    _: Annotated[None, Depends(_require_token)] = None,
):
    now = datetime.now(tz=UTC)
    weather, electricity, transport = await _fetch_data()
    return templates.TemplateResponse(
        request,
        "display.html",
        _build_context(now, weather, electricity, transport, width, height),
    )


async def _render_display(width: int, height: int, fmt: str) -> Response:
    now = datetime.now(tz=UTC)
    cache_key = (width, height, fmt)
    entry = _image_cache.get(cache_key)

    if entry and entry.is_fresh(now):
        return Response(content=entry.data, media_type=f"image/{fmt}")

    weather, electricity, transport = await _fetch_data()
    ctx = _build_context(now, weather, electricity, transport, width, height)
    html = templates.env.get_template("display.html").render(ctx)
    image = await render(html, width, height, fmt)

    _image_cache[cache_key] = _CacheEntry(data=image, time=now)

    return Response(content=image, media_type=f"image/{fmt}")


@app.get("/display.png")
async def get_display_png(
    width: Annotated[int, Query()] = WIDTH,
    height: Annotated[int, Query()] = HEIGHT,
    _: Annotated[None, Depends(_require_token)] = None,
):
    return await _render_display(width, height, "png")


@app.get("/display.jpg")
async def get_display_jpg(
    width: Annotated[int, Query()] = WIDTH,
    height: Annotated[int, Query()] = HEIGHT,
    _: Annotated[None, Depends(_require_token)] = None,
):
    return await _render_display(width, height, "jpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
