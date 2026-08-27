"""Tests for the shared menu cache in app.menu."""

from datetime import UTC, date, datetime, timedelta

from app.menu import Dish, MenuDay, _MenuCache

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
TTL = timedelta(hours=1)


def _cache_with_data() -> _MenuCache:
    day = MenuDay(date=date(2026, 8, 27), dishes=[Dish(name="Lohikeitto")])
    return _MenuCache(data=[day], time=NOW)


def test_an_empty_cache_is_never_fresh() -> None:
    assert not _MenuCache().is_fresh(NOW, TTL)


def test_a_cache_without_a_timestamp_is_not_fresh() -> None:
    day = MenuDay(date=date(2026, 8, 27), dishes=[])
    assert not _MenuCache(data=[day]).is_fresh(NOW, TTL)


def test_a_cache_without_data_is_not_fresh() -> None:
    assert not _MenuCache(time=NOW).is_fresh(NOW, TTL)


def test_is_fresh_within_the_ttl() -> None:
    assert _cache_with_data().is_fresh(NOW + TTL - timedelta(seconds=1), TTL)


def test_expires_exactly_at_the_ttl() -> None:
    assert not _cache_with_data().is_fresh(NOW + TTL, TTL)
