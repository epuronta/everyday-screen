"""Route-level tests for /display.png.

The data fetching and the Playwright render are stubbed out - what's under test
is the wiring between the schedule and the response, not the image itself.
"""

import logging
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient

from app import main, settings

VALID_BAND_SECONDS = {180, 600, 1800}


@pytest.fixture
def client(monkeypatch) -> AsyncGenerator[TestClient]:
    async def _no_data(_now, *, use_mock_weather: bool = False) -> tuple:  # noqa: ARG001
        return (None, None, None, None, None, None)

    async def _fake_render(_html, _width, _height) -> bytes:
        return b"\x89PNG\r\n\x1a\n"

    monkeypatch.setattr(main, "_fetch_data", _no_data)
    monkeypatch.setattr(main, "render", _fake_render)
    monkeypatch.setattr(settings, "API_TOKEN", "")
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 0)
    main._image_cache.clear()
    # Not used as a context manager on purpose: that would run the lifespan and
    # launch a real browser, which the stubbed render makes pointless.
    yield TestClient(main.app)
    main._image_cache.clear()


def test_serves_a_png(client: TestClient) -> None:
    response = client.get("/display.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_advertises_the_next_refresh(client: TestClient) -> None:
    """The header is the whole point of the schedule - assert it reaches the wire."""
    response = client.get("/display.png")
    assert int(response.headers["X-Next-Refresh"]) in VALID_BAND_SECONDS


def test_a_cached_response_still_advertises_the_next_refresh(
    client: TestClient,
) -> None:
    """A hit late in a band must not hand out the interval the band opened with."""
    first = client.get("/display.png")
    second = client.get("/display.png")
    assert second.content == first.content  # served from cache
    assert int(second.headers["X-Next-Refresh"]) in VALID_BAND_SECONDS


def test_the_override_reaches_the_header(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 120)
    assert client.get("/display.png").headers["X-Next-Refresh"] == "120"


def test_an_override_below_the_floor_is_clamped(
    client: TestClient, monkeypatch
) -> None:
    """30s would be rejected on the device and become a 15-minute retry."""
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 30)
    assert client.get("/display.png").headers["X-Next-Refresh"] == "60"


def test_an_override_above_the_ceiling_is_clamped(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 99999)
    assert client.get("/display.png").headers["X-Next-Refresh"] == "21600"


def test_a_bad_token_is_rejected_before_anything_is_rendered(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "API_TOKEN", "secret")
    assert client.get("/display.png").status_code == 403
    assert client.get("/display.png?token=secret").status_code == 200


def test_an_out_of_range_override_warns_at_startup(monkeypatch, caplog) -> None:
    """Silently adjusting a configured value is worse than saying so once."""
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 30)
    with caplog.at_level(logging.WARNING, logger="app.main"):
        main._warn_on_clamped_override()
    assert "REFRESH_OVERRIDE_SECONDS=30s" in caplog.text
    assert "serving 60s" in caplog.text


def test_an_in_range_override_starts_up_quietly(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 120)
    with caplog.at_level(logging.WARNING, logger="app.main"):
        main._warn_on_clamped_override()
    assert caplog.text == ""


def test_no_override_starts_up_quietly(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "REFRESH_OVERRIDE_SECONDS", 0)
    with caplog.at_level(logging.WARNING, logger="app.main"):
        main._warn_on_clamped_override()
    assert caplog.text == ""
