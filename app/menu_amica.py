import json
import re
from datetime import UTC, date, datetime, timedelta

import httpx

from .menu import Dish, MenuDay, _MenuCache

CACHE_TTL = timedelta(hours=1)

# Anchored to </script> so the lazy .*? doesn't greedily stop at the first nested }
_INITIAL_MENU_RE = re.compile(
    r"window\.__INITIAL_MENU__\s*=\s*(\{.*?\});\s*</script>", re.DOTALL
)

_cache = _MenuCache()


def _parse(html: str) -> list[MenuDay]:
    match = _INITIAL_MENU_RE.search(html)
    if not match:
        msg = "__INITIAL_MENU__ not found in page"
        raise ValueError(msg)

    data = json.loads(match.group(1))
    days = []
    for day in data["weekMenu"]["menus"]:
        day_date = date.fromisoformat(day["date"][:10])  # strip the time component
        dishes = [
            Dish(name=m["name"].strip())
            for p in day["menuPackages"]
            if p["name"] == "Lounas"
            for m in p["meals"]
        ]
        if dishes:  # skip holidays — they appear as days with empty meal lists
            days.append(MenuDay(date=day_date, dishes=dishes))
    return days


async def get_amica_menu(url: str) -> list[MenuDay]:
    now = datetime.now(tz=UTC)

    if _cache.is_fresh(now, CACHE_TTL):
        return _cache.data  # type: ignore[return-value]

    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()

    data = _parse(resp.text)
    _cache.data = data
    _cache.time = now
    return data
