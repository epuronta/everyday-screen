from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from .renderer import render
from .weather import get_weather

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

PLACE = "Helsinki"
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


def _build_context(now: datetime, weather: object) -> dict:
    return {
        "time": now.astimezone().strftime("%H:%M"),
        "date": now.astimezone().strftime("%A, %b %d"),
        "weather": weather,
    }


@app.get("/")
async def read_display(request: Request):
    now = datetime.now(tz=UTC)
    weather = await get_weather(PLACE)
    return templates.TemplateResponse(
        request, "display.html", _build_context(now, weather)
    )


@app.get("/display.png")
async def get_display_image():
    now = datetime.now(tz=UTC)

    if _image_cache.is_fresh(now):
        return Response(content=_image_cache.data, media_type="image/png")

    weather = await get_weather(PLACE)
    ctx = _build_context(now, weather)
    html = templates.env.get_template("display.html").render(ctx)
    png = await render(html)

    _image_cache.data = png
    _image_cache.time = now

    return Response(content=png, media_type="image/png")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
