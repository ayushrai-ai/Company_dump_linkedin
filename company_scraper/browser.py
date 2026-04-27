from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from .exceptions import NetworkError

logger = logging.getLogger(__name__)


class BrowserManager:
    """Async context manager that owns Playwright + Chromium + context + page."""

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        viewport: Optional[Dict[str, int]] = None,
        user_agent: Optional[str] = None,
        **launch_options: Any,
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.viewport = viewport or {"width": 1280, "height": 720}
        self.user_agent = user_agent
        self.launch_options = launch_options

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                **self.launch_options,
            )

            context_opts: Dict[str, Any] = {"viewport": self.viewport}
            if self.user_agent:
                context_opts["user_agent"] = self.user_agent

            self._context = await self._browser.new_context(**context_opts)
            self._page = await self._context.new_page()

            logger.info("Browser started (headless=%s)", self.headless)
        except Exception as e:
            await self.close()
            raise NetworkError(f"Failed to start browser: {e}")

    async def close(self) -> None:
        try:
            if self._page:
                await self._page.close()
                self._page = None
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception:
            # best-effort cleanup
            pass

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started.")
        return self._page

    async def save_session(self, filepath: str) -> None:
        if not self._context:
            raise RuntimeError("No browser context.")
        state = await self._context.storage_state()
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    async def load_session(self, filepath: str) -> None:
        """Recreate context using storage_state."""
        if not Path(filepath).exists():
            raise FileNotFoundError(filepath)
        if not self._browser:
            raise RuntimeError("Browser not started.")

        if self._context:
            await self._context.close()

        self._context = await self._browser.new_context(
            storage_state=filepath,
            viewport=self.viewport,
            user_agent=self.user_agent,
        )
        if self._page:
            await self._page.close()
        self._page = await self._context.new_page()