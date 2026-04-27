class ScraperError(Exception):
    """Base error for the custom scraper."""


class AuthenticationError(ScraperError):
    """Not logged in / blocked by authwall / checkpoint."""


class RateLimitError(ScraperError):
    """CAPTCHA / Too many requests / checkpoint detected."""

    def __init__(self, message: str, suggested_wait_time: int = 1800):
        super().__init__(message)
        self.suggested_wait_time = suggested_wait_time


class ElementNotFoundError(ScraperError):
    """Expected selector not found."""


class NetworkError(ScraperError):
    """Playwright / navigation / network failure."""