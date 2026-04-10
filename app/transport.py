import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

DIGITRANSIT_URL = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"
CACHE_TTL = timedelta(seconds=1)

_CODE_RESOLVE_QUERY = """
{ stops { code gtfsId } }
"""

_STOP_QUERY = """
query StopDepartures($gtfsId: String!, $n: Int!) {
  stop(id: $gtfsId) {
    name
    stoptimesWithoutPatterns(numberOfDepartures: $n) {
      serviceDay
      realtimeDeparture
      realtime
      headsign
      trip {
        route {
          shortName
        }
      }
    }
  }
}
"""

# Permanent cache: stop code → gtfsId (never changes)
_code_to_gtfs_id: dict[str, str] = {}


@dataclass
class StopConfig:
    code: str
    lines: set[str] | None = None
    walk_time_minutes: int = 0


@dataclass
class Departure:
    line: str
    headsign: str
    time: datetime  # local time


@dataclass
class StopDepartures:
    stop_id: str
    stop_name: str
    departures: list[Departure]
    walk_time_minutes: int = 0


@dataclass
class _Cache:
    data: list[StopDepartures] | None = None
    time: datetime | None = None

    def is_fresh(self, now: datetime) -> bool:
        if self.data is None or self.time is None:
            return False
        return now - self.time < CACHE_TTL


_cache = _Cache()


def _parse_departures(
    stop_id: str,
    stop_data: dict,
    stop: StopConfig,
) -> StopDepartures:
    departures = []
    for st in stop_data.get("stoptimesWithoutPatterns") or []:
        line = st["trip"]["route"]["shortName"]
        if stop.lines and line not in stop.lines:
            continue
        # serviceDay = Unix ts for midnight; realtimeDeparture = seconds from midnight
        t = datetime.fromtimestamp(st["serviceDay"] + st["realtimeDeparture"], tz=UTC)
        headsign = (
            st["headsign"]
            .split(" via ")[0]
            .removesuffix("(M)")
            .removesuffix(" (M)")
            .rstrip()
        )
        departures.append(Departure(line=line, headsign=headsign, time=t))
    return StopDepartures(
        stop_id=stop_id,
        stop_name=stop_data["name"],
        departures=departures,
        walk_time_minutes=stop.walk_time_minutes,
    )


async def get_transport(
    api_key: str,
    stops: list[StopConfig],
    departures_per_stop: int = 10,
) -> list[StopDepartures]:
    now = datetime.now(tz=UTC)

    if _cache.is_fresh(now):
        return _cache.data  # type: ignore[return-value]

    headers = {"digitransit-subscription-key": api_key}

    async with httpx.AsyncClient() as client:
        results = []
        # Resolve any unknown codes to gtfsIds (once, cached permanently)
        unknown = [s.code for s in stops if s.code not in _code_to_gtfs_id]
        if unknown:
            resp = await client.post(
                DIGITRANSIT_URL, headers=headers, json={"query": _CODE_RESOLVE_QUERY}
            )
            resp.raise_for_status()
            for s in resp.json()["data"]["stops"]:
                _code_to_gtfs_id[s["code"]] = s["gtfsId"]

        async def fetch_stop(stop: StopConfig) -> StopDepartures | None:
            gtfs_id = _code_to_gtfs_id.get(stop.code)
            if gtfs_id is None:
                return None
            # Over-fetch when filtering so enough remain after applying it
            n = (
                departures_per_stop * (len(stop.lines) + 1)
                if stop.lines
                else departures_per_stop
            )
            resp = await client.post(
                DIGITRANSIT_URL,
                headers=headers,
                json={"query": _STOP_QUERY, "variables": {"gtfsId": gtfs_id, "n": n}},
            )
            resp.raise_for_status()
            stop_data = resp.json()["data"]["stop"]
            if stop_data is None:
                return None
            stop_deps = _parse_departures(stop.code, stop_data, stop)
            stop_deps.departures = stop_deps.departures[:departures_per_stop]
            return stop_deps

        results = [
            r
            for r in await asyncio.gather(*[fetch_stop(s) for s in stops])
            if r is not None
        ]

    _cache.data = results
    _cache.time = now
    return results
