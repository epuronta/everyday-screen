# TODO — indirect findings

Things noticed but left alone — wrong scope, not urgent.

## Dependency upgrades

Every now and then (last executed: 2026-05-02), update uv dependencies. Update, verify that it works and create a feature branch out of it for me to verify.

## Battery voltage may be read under WiFi load

`readBattery()` is called after `connectWiFi()` in the firmware, so the reading
is taken while the radio is powered and possibly transmitting. That drags the
measured voltage down and is a plausible reason a fully charged battery reports
~80%. Worth trying the read *before* `connectWiFi()` and comparing across a few
wakes — needs the physical device, so it wasn't attempted.

## A truncated PNG hangs the device forever

Switching to `drawPngFromWeb(stream, ...)` also switched which library
download loop runs. The URL overload loops on
`while (http.connected() && len > 0)`; the stream overload it uses now loops on
`while (len > 0)` alone, with no connection check and no timeout. A response
that reports a Content-Length and then stops short — WiFi drop, Traefik giving
up mid-render — spins with the radio on until the battery is flat, rather than
failing to the error screen and the 15-minute fallback.

Not fixable from `main.cpp` without reimplementing the download and feeding
pngle directly, since the library exposes no `drawPngFromBuffer`. A task
watchdog around the fetch would turn the hang into a reboot loop, which is
better but still not good. Needs a decision.

## No HTTP timeout is set on the fetch

`HTTPClient` defaults to a 5s read timeout, and a cache-miss `/display.png`
costs a Playwright render plus six upstream fetches. Worth measuring the p99
before picking a number, but the default is not obviously enough.

## The image cache barely hits any more

`battery` is part of the cache key, and every wake reports a slightly different
voltage, so the device always misses. Correct — the reading is baked into the
image — but the 1-minute TTL now only ever helps the browser and
`make screenshot`. If burst protection matters, the fix is to quantise the
voltage into the key rather than to drop it.

## README claims 5 departures per stop

`DEPARTURE_CAP` is 4. Pre-dates the refresh work; one of the two is wrong.

## Untested layers

Commit 0 covered the pure logic (parsers, geometry, schedule). Deliberately left
out:

- **The `get_*` network fetchers.** Each sits behind a module-level `_cache`
  global, so testing them needs both httpx transport mocking and cache-reset
  fixtures, or the tests go order-dependent. Real work, not a footnote.
- **`renderer.py`** — Playwright, slow, and a golden-image test would be brittle.
- **Route-level tests** — would need the whole fetch layer stubbed.

## Tests depend on a gitignored file

Anything importing `app.main` needs `app/settings_local.py` to exist, which is
gitignored. Fine locally; would need solving before this could run in CI.

## FIXMEs planted during commit 0

Each has a test pinning the current behaviour, so changing them is deliberate
rather than accidental:

- `_catmull_rom_path` raises on an empty point list (`app/electricity.py`)
- The sparkline y-scale goes negative below -10 c/kWh and the axis labels vanish
  entirely (`app/electricity.py`)
- A null headsign takes out an entire stop rather than degrading
  (`app/transport.py`)
- The unreachable `" (M)"` removesuffix in `_parse_departures`
  (`app/transport.py`)
- `prepare_display` only merges consecutive same-day events, so unsorted input
  renders a duplicate day heading (`app/calendar.py`)

## `.text-ghost` is now a misnomer

It was `--g3` (genuinely ghostly); the footer needed to be readable, so it's
`--g2` now — same shade as `.text-secondary`, differing only in font size.
Either rename it or fold the two together.
