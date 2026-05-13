from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class Dish:
    name: str


@dataclass
class MenuDay:
    date: date
    dishes: list[Dish]


@dataclass
class _MenuCache:
    data: list[MenuDay] | None = None
    time: datetime | None = None

    def is_fresh(self, now: datetime, ttl: timedelta) -> bool:
        if self.data is None or self.time is None:
            return False
        return now - self.time < ttl
