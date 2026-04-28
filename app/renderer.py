import asyncio
import logging

from playwright.async_api import Browser, Playwright, async_playwright

WIDTH = 1200
HEIGHT = 825

log = logging.getLogger(__name__)

_playwright: Playwright | None = None
_browser: Browser | None = None
_lock = asyncio.Lock()


async def startup() -> None:
    global _playwright, _browser  # noqa: PLW0603
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch()


async def shutdown() -> None:
    global _playwright, _browser  # noqa: PLW0603
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


async def _ensure_browser() -> None:
    global _playwright, _browser  # noqa: PLW0603
    async with _lock:
        if _browser is not None and _browser.is_connected():
            return
        log.warning("Browser not connected, reconnecting")
        if _playwright is None:
            _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch()


async def _do_render(html: str, width: int, height: int) -> bytes:
    assert _browser is not None  # noqa: S101
    page = await _browser.new_page()
    try:
        await page.set_viewport_size({"width": width, "height": height})
        await page.set_content(html, wait_until="networkidle")
        return await page.screenshot(type="png")
    finally:
        await page.close()


async def render(html: str, width: int = WIDTH, height: int = HEIGHT) -> bytes:
    try:
        return await _do_render(html, width, height)
    except Exception:  # noqa: BLE001
        log.warning("Render failed, reconnecting browser and retrying")
        await _ensure_browser()
        return await _do_render(html, width, height)
