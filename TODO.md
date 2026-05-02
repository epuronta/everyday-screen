# TODO — indirect findings

Things noticed but left alone — wrong scope, not urgent.

## Dependency upgrades

Every now and then (last executed: unknown), update uv dependencies. Update, verify that it works and create a feature branch out of it for me to verify.



## `?futureevents=true` lives in the settings URL

The query param that filters the iCal feed to future-only events is
manually appended to `GCAL_ICAL_URL` in settings. `calendar.py` could
append it transparently so the settings value is just the base URL.

