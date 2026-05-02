from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar

CACHE_TTL = timedelta(minutes=5)
_LOOKAHEAD_DAYS = 14
_MAX_EVENTS = 5


@dataclass
class CalendarEvent:
    title: str
    start: datetime
    end: datetime
    all_day: bool


@dataclass
class CalendarEventDisplay:
    time_label: str
    title: str


@dataclass
class CalendarDayGroup:
    label: str
    events: list[CalendarEventDisplay]


@dataclass
class _Cache:
    data: list[CalendarEvent] | None = None
    time: datetime | None = None

    def is_fresh(self, now: datetime) -> bool:
        if self.data is None or self.time is None:
            return False
        return now - self.time < CACHE_TTL


_cache = _Cache()


def _to_utc_datetime(dt: datetime | date) -> datetime:
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return datetime(dt.year, dt.month, dt.day, tzinfo=UTC)


def _parse_events(raw: bytes, today: date) -> list[CalendarEvent]:
    cal = Calendar.from_ical(raw)
    events: list[CalendarEvent] = []
    horizon = today + timedelta(days=_LOOKAHEAD_DAYS)

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        if dtstart is None:
            continue

        raw_start = dtstart.dt
        raw_end = dtend.dt if dtend else raw_start
        all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)

        start = _to_utc_datetime(raw_start)
        end = _to_utc_datetime(raw_end)

        start_date = start.date()
        end_date = end.date()

        if not (
            today <= start_date <= horizon or (start_date < today and end_date > today)
        ):
            continue

        events.append(
            CalendarEvent(
                title=str(component.get("SUMMARY", "")),
                start=start,
                end=end,
                all_day=all_day,
            )
        )

    events.sort(key=lambda e: e.start)
    return events


def _day_label(d: date, today: date, fi_weekdays: list[str]) -> str:
    if d == today:
        return "Tänään"
    if d == today + timedelta(days=1):
        return "Huomenna"
    return f"{fi_weekdays[d.weekday()].capitalize()} {d.day}.{d.month}."


def prepare_display(
    events: list[CalendarEvent],
    now: datetime,
    tz: ZoneInfo,
    fi_weekdays: list[str],
) -> list[CalendarDayGroup]:
    today = now.astimezone(tz).date()
    groups: list[CalendarDayGroup] = []

    for event in events[:_MAX_EVENTS]:
        event_date = event.start.astimezone(tz).date()
        if event.all_day and event_date < today:
            event_date = today
        label = _day_label(event_date, today, fi_weekdays)

        if not groups or groups[-1].label != label:
            groups.append(CalendarDayGroup(label=label, events=[]))

        time_label = (
            "" if event.all_day else event.start.astimezone(tz).strftime("%H:%M")
        )
        groups[-1].events.append(
            CalendarEventDisplay(time_label=time_label, title=event.title)
        )

    return groups


def _ensure_future_events(url: str) -> str:
    # Needed for Google Calendar feeds; skip if the caller already included it
    if "futureevents=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}futureevents=true"


async def get_calendar(ical_url: str) -> list[CalendarEvent]:
    now = datetime.now(tz=UTC)

    if _cache.is_fresh(now):
        return _cache.data  # type: ignore[return-value]

    url = _ensure_future_events(ical_url)
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, follow_redirects=True, timeout=10)
        resp.raise_for_status()

    today = now.date()
    _cache.data = _parse_events(resp.content, today)
    _cache.time = now
    return _cache.data
