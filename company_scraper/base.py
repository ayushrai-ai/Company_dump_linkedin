from __future__ import annotations

import logging
import random
from typing import Optional

from playwright.async_api import Page

from .exceptions import AuthenticationError
from .utils import detect_rate_limit, extract_text_safe, is_logged_in

logger = logging.getLogger(__name__)


class BaseScraper:
    """Shared utilities for LinkedIn scrapers (person/company/etc)."""

    def __init__(self, page: Page):
        self.page = page

    async def navigate_and_wait(self, url: str, timeout_ms: int = 60000) -> None:
        await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await detect_rate_limit(self.page)

    async def ensure_logged_in(self) -> None:
        if not await is_logged_in(self.page):
            raise AuthenticationError(
                "Not logged in. Load a valid LinkedIn session before scraping."
            )

    async def wait_and_focus(self, seconds: float) -> None:
        # Randomize lightly around the requested value, same spirit as company scraper.
        min_ms = max(50, int(seconds * 700))
        max_ms = max(min_ms, int(seconds * 1300))
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))

    async def human_pause(self, min_ms: int = 400, max_ms: int = 1200) -> None:
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))

    async def human_browse_noise(self) -> None:
        """Best-effort human-like noise: variable dwell, scrolls, and mouse movement."""
        try:
            await self.human_pause(500, 1600)

            if random.random() < 0.9:
                await self.page.mouse.wheel(0, random.randint(250, 900))
                await self.human_pause(250, 700)

            if random.random() < 0.6:
                await self.page.mouse.move(
                    random.randint(120, 900),
                    random.randint(120, 650),
                    steps=random.randint(8, 20),
                )
                await self.human_pause(180, 500)

            if random.random() < 0.3:
                await self.page.mouse.wheel(0, random.randint(-400, -100))
                await self.human_pause(200, 500)
        except Exception:
            return

    async def scroll_page_to_half(self) -> None:
        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        except Exception:
            pass

    async def scroll_page_to_bottom(self, pause_time: float = 0.5, max_scrolls: int = 5) -> None:
        try:
            last_height = await self.page.evaluate("document.body.scrollHeight")
        except Exception:
            return

        for _ in range(max_scrolls):
            try:
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self.page.wait_for_timeout(int(pause_time * 1000))
                new_height = await self.page.evaluate("document.body.scrollHeight")
            except Exception:
                return
            if new_height == last_height:
                return
            last_height = new_height

    async def safe_extract_text(self, selector: str, default: str = "") -> str:
        return await extract_text_safe(self.page, selector, default=default)

    async def get_attribute_safe(
        self, selector: str, attribute: str, default: str = ""
    ) -> str:
        try:
            loc = self.page.locator(selector).first
            val = await loc.get_attribute(attribute, timeout=2000)
            return (val or "").strip() or default
        except Exception:
            return default
