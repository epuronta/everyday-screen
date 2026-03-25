import asyncio

from playwright.async_api import async_playwright


async def capture_display():
    async with async_playwright() as p:
        # Change 'chromium' to 'firefox' if preferred
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Set this to your target display resolution
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # Navigate to your local running FastAPI server
        await page.goto("http://localhost:8000")

        # Wait for fonts/images to load
        await page.wait_for_timeout(1000)

        # Save the image
        await page.screenshot(path="latest_display.png")
        print("Image rendered: latest_display.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(capture_display())
