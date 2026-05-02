# TODO — indirect findings

Things noticed but left alone — wrong scope, not urgent.

## Dependency upgrades

Every now and then (last executed: unknown), update uv dependencies. Update, verify that it works and create a feature branch out of it for me to verify.



## Transport magic numbers buried in template

`display.html`: departure cap (`ns.shown < 4`) and lookahead window
(`timedelta(minutes=40)`) are magic numbers in Jinja2. They belong as
Python-level constants alongside the stop config.

## `?futureevents=true` lives in the settings URL

The query param that filters the iCal feed to future-only events is
manually appended to `GCAL_ICAL_URL` in settings. `calendar.py` could
append it transparently so the settings value is just the base URL.

## Calendar: recurring events not expanded

`icalendar` only sees the base VEVENT, not individual occurrences.
A weekly recurring event will appear once (or not at all if the base
date is past). Needs `rrulestr` expansion from the `icalendar` library.

## Calendar: multi-day all-day events group under start date

An event spanning Mon–Thu that started before today is included but
grouped under its start date, which may be in the past. Should appear
under today instead when it's already in progress.

## Calendar: `_MAX_EVENTS` slices before grouping by day

Today+tomorrow visibility is not guaranteed — 5 events on the same day
would consume the cap and hide tomorrow. Should ensure at least one day
boundary is crossed before cutting off.
