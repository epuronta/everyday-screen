import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from .electricity import get_electricity
from .renderer import HEIGHT, WIDTH, render
from .transport import get_transport
from .weather import get_weather

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

PLACE = os.environ["FMI_CITY"]
DIGITRANSIT_API_KEY = os.environ["DIGITRANSIT_API_KEY"]
HSL_STOPS = [s.strip() for s in os.environ["HSL_STOPS"].split(",")]
HSL_LINES: set[str] | None = (
    {line.strip() for line in os.environ["HSL_LINES"].split(",")}
    if os.environ.get("HSL_LINES")
    else None
)
IMAGE_CACHE_TTL = timedelta(minutes=1)


@dataclass
class _ImageCache:
    data: bytes | None = None
    time: datetime | None = field(default=None)

    def is_fresh(self, now: datetime) -> bool:
        if self.data is None or self.time is None:
            return False
        return now - self.time < IMAGE_CACHE_TTL


_image_cache = _ImageCache()


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


@app.get("/")
async def read_display(
    request: Request,
    width: Annotated[int, Query()] = WIDTH,
    height: Annotated[int, Query()] = HEIGHT,
):
    now = datetime.now(tz=UTC)
    weather, electricity, transport = await asyncio.gather(
        get_weather(PLACE),
        get_electricity(),
        get_transport(DIGITRANSIT_API_KEY, HSL_STOPS, HSL_LINES),
    )
    return templates.TemplateResponse(
        request,
        "display.html",
        _build_context(now, weather, electricity, transport, width, height),
    )


@app.get("/display.png")
async def get_display_image(
    width: Annotated[int, Query()] = WIDTH,
    height: Annotated[int, Query()] = HEIGHT,
):
    now = datetime.now(tz=UTC)
    is_default_size = width == WIDTH and height == HEIGHT

    if is_default_size and _image_cache.is_fresh(now):
        return Response(content=_image_cache.data, media_type="image/png")

    weather, electricity, transport = await asyncio.gather(
        get_weather(PLACE),
        get_electricity(),
        get_transport(DIGITRANSIT_API_KEY, HSL_STOPS, HSL_LINES),
    )
    ctx = _build_context(now, weather, electricity, transport, width, height)
    html = templates.env.get_template("display.html").render(ctx)
    png = await render(html, width, height)

    _image_cache.data = png
    _image_cache.time = now

    return Response(content=png, media_type="image/png")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
