"""Module for taking screenshots of web pages in different screen sizes."""

import asyncio
from pathlib import Path

from common.browser import BROWSER_TIMEOUT, Browser, launch_browser
from common.logger import common_logger
from common.config import PageConfig


async def capture_page_screenshots(config: PageConfig, overwrite: bool = False) -> None:
    """Capture screenshots for a page based on the provided configuration."""

    tasks = _prepare_tasks(config, overwrite)
    if tasks:
        async with launch_browser() as browser:
            await asyncio.gather(*[_capture_with_viewport(browser, config.url, size, path) for size, path in tasks])


async def capture_screenshots_with_browser(browser: Browser, config: PageConfig, overwrite: bool = False) -> None:
    """Capture screenshots using an existing Browser instance."""
    tasks = _prepare_tasks(config, overwrite)
    if tasks:
        await asyncio.gather(*[_capture_with_viewport(browser, config.url, size, path) for size, path in tasks])


async def _capture_with_viewport(browser: Browser, page_url: str, viewport_size: str, save_path: str) -> None:
    """Capture a screenshot at a specific viewport size."""
    width_str, height_str = viewport_size.split("x", maxsplit=1)
    width, height = int(width_str), int(height_str)

    context = await browser.new_context(viewport={"width": width, "height": height})
    page = await context.new_page()
    try:
        response = await page.goto(page_url, timeout=BROWSER_TIMEOUT, wait_until="networkidle")

        # Check for 404 or other error status codes
        if response and response.status == 404:
            raise FileNotFoundError(f"Page not found (404): {page_url}")
        if response and response.status >= 400:
            raise RuntimeError(f"HTTP Error {response.status}: {page_url}")

        await page.screenshot(
            path=save_path,
            full_page=True,
            animations="disabled",
            timeout=BROWSER_TIMEOUT,
        )
        common_logger.info("Screenshot captured: %s (%s)", page_url, viewport_size)
    except Exception as exc:
        common_logger.error("Failed screenshot %s (%s): %s", page_url, viewport_size, exc)
        raise
    finally:
        await context.close()


def _prepare_tasks(config: PageConfig, overwrite: bool) -> list[tuple[str, str]]:
    """Build a list of (viewport, save_path) tasks based on config.screenshots."""
    planned: list[tuple[str, str]] = []
    for size, screenshot_path in config.screenshots.items():
        save_path = Path(screenshot_path)
        if save_path.exists() and not overwrite:
            # common_logger.info("Skip existing screenshot %s", save_path)
            continue
        save_path.parent.mkdir(parents=True, exist_ok=True)
        planned.append((size, screenshot_path))
    return planned
