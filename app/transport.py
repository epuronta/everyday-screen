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
class Departure:
    line: str
    headsign: str
    time: datetime  # local time


@dataclass
class StopDepartures:
    stop_id: str
    stop_name: str
    departures: list[Departure]


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
    line_filter: set[str] | None,
) -> StopDepartures:
    departures = []
    for st in stop_data.get("stoptimesWithoutPatterns") or []:
        line = st["trip"]["route"]["shortName"]
        if line_filter and line not in line_filter:
            continue
        # serviceDay = Unix ts for midnight; realtimeDeparture = seconds from midnight
        t = datetime.fromtimestamp(st["serviceDay"] + st["realtimeDeparture"], tz=UTC)
        headsign = st["headsign"].split(" via ")[0]
        departures.append(Departure(line=line, headsign=headsign, time=t))
    return StopDepartures(
        stop_id=stop_id,
        stop_name=stop_data["name"],
        departures=departures,
    )


async def get_transport(
    api_key: str,
    stop_ids: list[str],
    line_filter: set[str] | None = None,
    departures_per_stop: int = 5,
) -> list[StopDepartures]:
    now = datetime.now(tz=UTC)

    if _cache.is_fresh(now):
        return _cache.data  # type: ignore[return-value]

    headers = {"digitransit-subscription-key": api_key}

    async with httpx.AsyncClient() as client:
        results = []
        # Resolve any unknown codes to gtfsIds (once, cached permanently)
        unknown = [c for c in stop_ids if c not in _code_to_gtfs_id]
        if unknown:
            resp = await client.post(
                DIGITRANSIT_URL, headers=headers, json={"query": _CODE_RESOLVE_QUERY}
            )
            resp.raise_for_status()
            for s in resp.json()["data"]["stops"]:
                _code_to_gtfs_id[s["code"]] = s["gtfsId"]

        async def fetch_stop(stop_code: str) -> StopDepartures | None:
            gtfs_id = _code_to_gtfs_id.get(stop_code)
            if gtfs_id is None:
                return None
            # Over-fetch when filtering so enough remain after applying it
            n = (
                departures_per_stop * (len(line_filter) + 1)
                if line_filter
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
            stop_deps = _parse_departures(stop_code, stop_data, line_filter)
            stop_deps.departures = stop_deps.departures[:departures_per_stop]
            return stop_deps

        results = [
            r
            for r in await asyncio.gather(*[fetch_stop(c) for c in stop_ids])
            if r is not None
        ]

    _cache.data = results
    _cache.time = now
    return results
