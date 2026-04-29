# TODO — indirect findings

Things noticed but left alone — wrong scope, not urgent.

## Grey levels need clarification

Note that anything lighter than --g3 is practically invisible on the screen and thus unusable in practice. Generally, prefer "surely dark enough" over "just about visible".

## `_image_cache` type annotation wrong

`main.py`: annotated as `dict[tuple[int, int, str], _CacheEntry]` but
keyed as `(width, height)` — a 2-tuple, not 3-tuple. Pre-existing, no
runtime impact.

## Transport magic numbers buried in template

`display.html`: departure cap (`ns.shown < 4`) and lookahead window
(`timedelta(minutes=40)`) are magic numbers in Jinja2. They belong as
Python-level constants alongside the stop config.

## `?futureevents=true` lives in the settings URL

The query param that filters the iCal feed to future-only events is
manually appended to `GCAL_ICAL_URL` in settings. `calendar.py` could
append it transparently so the settings value is just the base URL.
