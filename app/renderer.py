from playwright.async_api import async_playwright

WIDTH = 1920
HEIGHT = 1080


async def render(html: str) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_viewport_size({"width": WIDTH, "height": HEIGHT})
        await page.set_content(html, wait_until="networkidle")
        png = await page.screenshot()
        await browser.close()
        return png
