from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

SPOT_URL = "https://api.spot-hinta.fi/Today"
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
