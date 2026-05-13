from datetime import UTC, date, datetime, timedelta

import httpx

from .menu import Dish, MenuDay, _MenuCache

CACHE_TTL = timedelta(hours=1)

# "Lounas." (with period) is the meat option; "Lounas" (no period) is vegetarian.
# The school only needs the meat option — kids pick separately.
_RELEVANT_MEALS = {"Lounas."}

_cache = _MenuCache()


def _parse_days(raw: list[dict]) -> list[MenuDay]:
    days = []
    for day in raw:
        day_date = date.fromisoformat(day["Date"][:10])
        dishes: list[Dish] = []
        for meal in day.get("Meals") or []:
            if meal.get("MealName") not in _RELEVANT_MEALS:
                continue
            dishes.extend(
                Dish(name=d["DishName"].strip()) for d in meal.get("Dishes") or []
            )
        if dishes:
            days.append(MenuDay(date=day_date, dishes=dishes))
    return days


# x-requested-with is required — the server rejects requests without it.
# No session cookie or CSRF token needed despite the Angular SPA using them.
_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "x-requested-with": "XMLHttpRequest",
}


async def get_menu(
    url: str,
    restaurant_id: str,
    diner_group_id: str,
    *,
    days_ahead: int = 4,
) -> list[MenuDay]:
    now = datetime.now(tz=UTC)

    if _cache.is_fresh(now, CACHE_TTL):
        return _cache.data  # type: ignore[return-value]

    today = now.date()
    end = today + timedelta(days=days_ahead)

    params = {
        "Id": restaurant_id,
        "StartDate": today.isoformat(),
        "EndDate": end.isoformat(),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            params=params,
            headers=_HEADERS,
            # SPA sends the full diner group object, but only these two fields matter.
            json={"DinerGroupId": diner_group_id, "SuitabilityDietIds": []},
        )
        resp.raise_for_status()
        data = _parse_days(resp.json())

    _cache.data = data
    _cache.time = now
    return data
