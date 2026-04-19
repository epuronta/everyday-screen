import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

SPOT_URL = "https://api.spot-hinta.fi/TodayAndDayForward?priceResolution=60"
CHEAP_THRESHOLD = 5.0  # c/kWh
EXPENSIVE_THRESHOLD = 15.0  # c/kWh

CACHE_TTL = timedelta(hours=1)
CATMULL_ROM_TENSION = 0.3


def _catmull_rom_path(pts: list[tuple[float, float]]) -> str:
    """Convert a list of (x, y) points to a smooth SVG cubic bezier path string."""
    n = len(pts)
    parts = [f"M {pts[0][0]},{pts[0][1]}"]
    for i in range(1, n):
        x0, y0 = pts[i - 2] if i >= 2 else pts[0]  # noqa: PLR2004
        x1, y1 = pts[i - 1]
        x2, y2 = pts[i]
        x3, y3 = pts[i + 1] if i + 1 < n else pts[-1]
        cp1x = round(x1 + (x2 - x0) * CATMULL_ROM_TENSION, 1)
        cp1y = round(y1 + (y2 - y0) * CATMULL_ROM_TENSION, 1)
        cp2x = round(x2 - (x3 - x1) * CATMULL_ROM_TENSION, 1)
        cp2y = round(y2 - (y3 - y1) * CATMULL_ROM_TENSION, 1)
        parts.append(f"C {cp1x},{cp1y} {cp2x},{cp2y} {x2},{y2}")
    return " ".join(parts)


@dataclass
class SpotPrice:
    time: datetime
    price: float  # c/kWh incl. VAT


@dataclass
class ElectricityData:
    hours: list[SpotPrice]

    def current(self, now: datetime, tz: ZoneInfo) -> SpotPrice | None:
        current_hour = now.astimezone(tz).replace(minute=0, second=0, microsecond=0)
        for h in self.hours:
            if (
                h.time.astimezone(tz).replace(minute=0, second=0, microsecond=0)
                == current_hour
            ):
                return h
        return None

    def classify(self, price: float) -> str:
        if price <= CHEAP_THRESHOLD:
            return "cheap"
        if price >= EXPENSIVE_THRESHOLD:
            return "expensive"
        return "ok"

    def sparkline(
        self,
        now: datetime,
        tz: ZoneInfo,
        width: int = 320,
        height: int = 56,
    ) -> dict:
        """Pre-compute SVG data for a fixed 48h window: today 00:00 → tomorrow 23:00.

        Today always occupies the left half, tomorrow the right — stable layout
        regardless of whether tomorrow's data is available yet.
        """
        midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        window_end = midnight + timedelta(hours=47)  # tomorrow 23:00

        today = now.astimezone(tz).date()
        hours = sorted(
            [h for h in self.hours if h.time.astimezone(tz).date() >= today],
            key=lambda h: h.time,
        )
        # Need at least today's data to render anything useful
        if not hours:
            return {}

        max_p = max(h.price for h in hours)
        y_max = (
            math.ceil(max_p / 10) * 10 or 10
        )  # at least 10c so we don't divide by zero

        pad_top = 14  # needs room for the top threshold label (font-size 11)
        pad_bottom = 20  # extra room so the line never collides with hour labels
        pad_left = 30  # room for left-side y-axis labels
        now_hour = now.astimezone(tz).replace(minute=0, second=0, microsecond=0)

        # Fixed 48h window — x position is independent of how much data is available
        t_start = midnight.astimezone(UTC)
        total_seconds = (window_end.astimezone(UTC) - t_start).total_seconds()

        def time_to_x(t: datetime) -> float:
            return round(
                pad_left
                + (t - t_start).total_seconds() / total_seconds * (width - pad_left),
                1,
            )

        def price_to_y(price: float) -> float:
            return round(
                pad_top + (height - pad_top - pad_bottom) * (1 - price / y_max), 1
            )

        pts = []
        current_x = None
        current_y = None

        for h in hours:
            x = time_to_x(h.time + timedelta(minutes=30))  # centre of the hour
            y = price_to_y(h.price)
            pts.append((x, y))
            if (
                h.time.astimezone(tz).replace(minute=0, second=0, microsecond=0)
                == now_hour
            ):
                current_x = x
                current_y = y

        path_d = _catmull_rom_path(pts)

        thresholds = []
        for price in range(0, y_max + 1, 10):
            y = price_to_y(float(price))
            thresholds.append({"y": y, "label": str(price)})

        # Dividers at every 2nd hour across the full 48h window
        dividers = []
        t = midnight
        while t <= window_end:
            x = time_to_x(t.astimezone(UTC))
            dividers.append(
                {
                    "x": x,
                    "label": str(t.hour),
                    "day_boundary": t.hour == 0 and t > midnight,
                }
            )
            t += timedelta(hours=2)

        return {
            "path_d": path_d,
            "current_x": current_x,
            "current_y": current_y,
            "thresholds": thresholds,
            "dividers": dividers,
            "width": width,
            "height": height,
            "pad_left": pad_left,
        }


@dataclass
class _Cache:
    data: ElectricityData | None = None
    time: datetime | None = field(default=None)

    def is_fresh(self, now: datetime) -> bool:
        if self.data is None or self.time is None:
            return False
        return now - self.time < CACHE_TTL


_cache = _Cache()


async def get_electricity() -> ElectricityData:
    now = datetime.now(tz=UTC)

    if _cache.is_fresh(now):
        return _cache.data  # type: ignore[return-value]

    async with httpx.AsyncClient() as client:
        resp = await client.get(SPOT_URL)
        resp.raise_for_status()

    hours = [
        SpotPrice(
            time=datetime.fromisoformat(item["DateTime"]),
            price=item["PriceWithTax"] * 100,  # API returns €/kWh, convert to c/kWh
        )
        for item in resp.json()
    ]

    _cache.data = ElectricityData(hours=hours)
    _cache.time = now

    return _cache.data
