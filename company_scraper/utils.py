from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, Optional, TypeVar

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .exceptions import RateLimitError, ElementNotFoundError

logger = logging.getLogger(__name__)
T = TypeVar("T")


def retry_async(max_attempts: int = 3, backoff: float = 2.0, exceptions: tuple[type[Exception], ...] = (Exception,)):
    """Retry decorator for async functions."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts - 1:
                        wait_s = backoff ** attempt
                        logger.warning("Attempt %s/%s failed: %s. Retrying in %ss", attempt + 1, max_attempts, e, wait_s)
                        await asyncio.sleep(wait_s)
            assert last_exc is not None
            raise last_exc
        return wrapper
    return decorator


async def detect_rate_limit(page: Page) -> None:
    """Very lightweight detection: checkpoint/authwall/captcha/text hints."""
    url = page.url or ""
    if any(x in url for x in ["linkedin.com/checkpoint", "authwall", "/challenge", "/uas/login"]):
        raise RateLimitError(f"LinkedIn checkpoint/authwall detected (url={url})", suggested_wait_time=3600)

    # CAPTCHA iframe patterns (best-effort)
    try:
        captcha_count = await page.locator('iframe[title*="captcha" i], iframe[src*="captcha" i]').count()
        if captcha_count > 0:
            raise RateLimitError("CAPTCHA detected. Manual intervention required.", suggested_wait_time=3600)
    except Exception:
        pass

    # Text hints — use LinkedIn-specific phrases only. Generic English (e.g.
    # "slow down", "try again later", "rate limit") appears in normal profile
    # content (posts, recommendations) and caused false positives.
    try:
        body = await page.locator("body").text_content(timeout=1000)
        if body:
            body_l = body.lower()
            patterns = [
                "we've detected unusual activity",
                "weve detected unusual activity",
                "temporarily restricted from",
                "you've been restricted",
                "youve been restricted",
                "weekly commercial use limit",
                "you've reached the weekly",
                "youve reached the weekly",
                "429 too many requests",
            ]
            for p in patterns:
                if p in body_l:
                    raise RateLimitError(
                        f"LinkedIn rate-limit phrase matched: '{p}'",
                        suggested_wait_time=1800,
                    )
    except PlaywrightTimeoutError:
        pass


async def is_logged_in(page: Page) -> bool:
    """Fail-fast check + nav element check + URL fallback."""
    try:
        url = page.url or ""
        blockers = ["/login", "/authwall", "/checkpoint", "/challenge", "/uas/login"]
        if any(b in url for b in blockers):
            return False

        # nav hints (LinkedIn changes often; keep broad)
        sel = 'nav a[href*="/feed"], nav a[href*="/mynetwork"], nav button:has-text("Home")'
        return await page.locator(sel).count() > 0 or any(x in url for x in ["/feed", "/mynetwork", "/notifications", "/messaging"])
    except Exception:
        return False


async def wait_for_element_smart(
    page: Page,
    selector: str,
    timeout_ms: float = 5000,
    state: str = "visible",
    context: Optional[str] = None,
) -> None:
    try:
        await page.wait_for_selector(selector, timeout=timeout_ms, state=state)
    except PlaywrightTimeoutError:
        ctx = f" ({context})" if context else ""
        raise ElementNotFoundError(f"Could not find element: {selector}{ctx}")


async def extract_text_safe(page: Page, selector: str, default: str = "", timeout_ms: float = 2000) -> str:
    try:
        loc = page.locator(selector).first
        txt = await loc.text_content(timeout=timeout_ms)
        return (txt or "").strip() or default
    except Exception:
        return default