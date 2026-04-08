from playwright.async_api import async_playwright

WIDTH = 1200
HEIGHT = 825


async def render(
    html: str, width: int = WIDTH, height: int = HEIGHT, fmt: str = "png"
) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_viewport_size({"width": width, "height": height})
        await page.set_content(html, wait_until="networkidle")
        image = await page.screenshot(type=fmt)
        await browser.close()
        return image
