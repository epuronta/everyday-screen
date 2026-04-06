from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

SPOT_URL = "https://api.spot-hinta.fi/Today"
CHEAP_THRESHOLD = 5.0  # c/kWh
EXPENSIVE_THRESHOLD = 15.0  # c/kWh
SPARKLINE_HOUR_START = 6
SPARKLINE_HOUR_END = 23
CACHE_TTL = timedelta(hours=1)


@dataclass
class SpotPrice:
    time: datetime
    price: float  # c/kWh incl. VAT


@dataclass
class ElectricityData:
    hours: list[SpotPrice]

    def current(self, now: datetime) -> SpotPrice | None:
        current_hour = now.astimezone().replace(minute=0, second=0, microsecond=0)
        for h in self.hours:
            if h.time.replace(minute=0, second=0, microsecond=0) == current_hour:
                return h
        return None

    def classify(self, price: float) -> str:
        if price <= CHEAP_THRESHOLD:
            return "cheap"
        if price >= EXPENSIVE_THRESHOLD:
            return "expensive"
        return "ok"

    def sparkline(self, now: datetime, width: int = 320, height: int = 56) -> dict:
        """Pre-compute SVG data for today's hourly prices."""
        today = now.astimezone().date()
        hours = sorted(
            [
                h
                for h in self.hours
                if h.time.astimezone().date() == today
                and SPARKLINE_HOUR_START
                <= h.time.astimezone().hour
                <= SPARKLINE_HOUR_END
            ],
            key=lambda h: h.time,
        )
        if len(hours) < 2:  # noqa: PLR2004
            return {}

        prices = [h.price for h in hours]
        min_p = min(prices)
        max_p = max(prices)
        if max_p == min_p:
            max_p = min_p + 1.0

        padding = 6
        n = len(hours)
        now_hour = now.astimezone().replace(minute=0, second=0, microsecond=0)

        points = []
        current_x = None
        current_y = None

        for i, h in enumerate(hours):
            x = round(i / (n - 1) * width, 1)
            y = round(
                padding
                + (height - 2 * padding) * (1 - (h.price - min_p) / (max_p - min_p)),
                1,
            )
            points.append(f"{x},{y}")
            if (
                h.time.astimezone().replace(minute=0, second=0, microsecond=0)
                == now_hour
            ):
                current_x = x
                current_y = y

        def price_to_y(price: float) -> float:
            return padding + (height - 2 * padding) * (
                1 - (price - min_p) / (max_p - min_p)
            )

        thresholds = []
        for price, label in [
            (CHEAP_THRESHOLD, str(CHEAP_THRESHOLD)),
            (EXPENSIVE_THRESHOLD, str(EXPENSIVE_THRESHOLD)),
        ]:
            y = round(price_to_y(price), 1)
            if padding <= y <= height - padding:
                thresholds.append({"y": y, "label": label})

        first_hour = hours[0].time.astimezone().hour
        last_hour = hours[-1].time.astimezone().hour
        hour_span = last_hour - first_hour
        dividers = [
            {"x": round((dh - first_hour) / hour_span * width, 1), "label": str(dh)}
            for dh in [8, 12, 16, 20]
            if first_hour < dh < last_hour
        ]

        return {
            "points": " ".join(points),
            "current_x": current_x,
            "current_y": current_y,
            "thresholds": thresholds,
            "dividers": dividers,
            "min_label": f"{min_p:.1f}",
            "max_label": f"{max_p:.1f}",
            "padding": padding,
            "width": width,
            "height": height,
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
