"""Common browser utilities using Playwright."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import Browser, async_playwright


BROWSER_TIMEOUT = 60_000  # 60 seconds


@asynccontextmanager
async def launch_browser() -> AsyncGenerator[Browser, None]:
    """Launch a Playwright browser instance."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            yield browser
        finally:
            await browser.close()
