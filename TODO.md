# TODO — indirect findings

Things noticed but left alone — wrong scope, not urgent.

## Layout reform (blocks calendar merge)

The current 2-column grid doesn't have enough vertical budget to fit
weather (2 days + rain charts), calendar events, transport, and electricity
all at once. Adding calendar to the clock cell overflows; splitting the
right column starves weather. Need a wider layout rethink before merging
feature/calendar. Options: 3-column grid, taller display, or compacting
weather/transport significantly.

## `_image_cache` type annotation wrong

`main.py`: annotated as `dict[tuple[int, int, str], _CacheEntry]` but
keyed as `(width, height)` — a 2-tuple, not 3-tuple. Pre-existing, no
runtime impact.

## Transport departure count hardcoded in template

`display.html`: `{% if ns.shown < 5 %}` — the 5 should be a Python-level
constant, not a magic number buried in the template.

## `?futureevents=true` lives in the settings URL

The query param that filters the iCal feed to future-only events is
manually appended to `GCAL_ICAL_URL` in settings. `calendar.py` could
append it transparently so the settings value is just the base URL.
