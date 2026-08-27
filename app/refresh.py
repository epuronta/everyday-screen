"""Decides how long the display device should sleep before its next refresh.

The device has no trustworthy clock, so this returns a duration rather than a
wake-up time. Durations are also DST-safe for free: all arithmetic below is on
absolute instants, and local wall-clock time is only ever used to decide which
band we're in and where the next band starts.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# A clamp to a band boundary can land arbitrarily close to now. Waking the
# device for a two-second nap costs more than it saves.
MIN_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True)
class Band:
    """A local wall-clock window, applied identically every day."""

    start: time
    end: time
    interval: timedelta


BANDS = (
    Band(time(6), time(9), timedelta(minutes=3)),
    Band(time(9), time(22), timedelta(minutes=10)),
)

# 22:00-06:00. Left implicit rather than spelled out as a band so the wrap over
# midnight doesn't need special-casing in the lookup.
NIGHT_INTERVAL = timedelta(minutes=30)

_BOUNDARIES = sorted({b.start for b in BANDS} | {b.end for b in BANDS})


def _band_for(local_time: time) -> Band | None:
    for band in BANDS:
        if band.start <= local_time < band.end:
            return band
    return None


def interval_for(local: datetime) -> timedelta:
    band = _band_for(local.time())
    return band.interval if band else NIGHT_INTERVAL


def _next_boundary(local: datetime) -> datetime:
    """Find the first band edge strictly after `local`, in local time."""
    tz = local.tzinfo
    for boundary in _BOUNDARIES:
        candidate = datetime.combine(local.date(), boundary, tzinfo=tz)
        if candidate > local:
            return candidate
    tomorrow = local.date() + timedelta(days=1)
    return datetime.combine(tomorrow, _BOUNDARIES[0], tzinfo=tz)


def next_refresh(now: datetime, tz: ZoneInfo) -> timedelta:
    """How long the device should sleep, starting from `now`.

    Clamped so a wake never overshoots into the following band. Without this,
    05:45 would sleep its full 30 minutes and miss the first quarter of the
    morning's tight cadence.
    """
    local = now.astimezone(tz)
    candidate = now + interval_for(local)
    boundary = _next_boundary(local)
    return max(min(candidate, boundary) - now, MIN_INTERVAL)
