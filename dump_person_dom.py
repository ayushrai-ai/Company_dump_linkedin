import asyncio
import re
from pathlib import Path

from company_scraper.browser import BrowserManager

PROFILE_URL_RE = re.compile(
    r"^(?:https?://)?(?:[a-z0-9-]+\.)?linkedin\.com/in/([^/?#]+)",
    flags=re.IGNORECASE,
)

SUBPATHS = {
    "main": "",
    "about": "details/about/",
    "experience": "details/experience/",
    "education": "details/education/",
    "skills": "details/skills/",
    "honors": "details/honors/",
    "recent_activity_all": "recent-activity/all/",
    "recent_activity_posts": "recent-activity/posts/",
    "contact_info": "overlay/contact-info/",
}


def normalize_profile(raw: str) -> tuple[str, str]:
    m = PROFILE_URL_RE.search((raw or "").strip())
    if not m:
        raise ValueError("Not a valid LinkedIn profile URL.")
    slug = m.group(1).strip().strip("/")
    return slug, f"https://www.linkedin.com/in/{slug}/"


async def scroll_full(page, rounds: int = 8, pause_ms: int = 700) -> None:
    try:
        last = await page.evaluate("document.body.scrollHeight")
    except Exception:
        return
    for _ in range(rounds):
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(pause_ms)
            new = await page.evaluate("document.body.scrollHeight")
        except Exception:
            return
        if new == last:
            return
        last = new


async def dump_url(page, url: str, out_path: Path) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        await scroll_full(page)
        html = await page.content()
        out_path.write_text(html, encoding="utf-8")
        print(f"saved {out_path}  ({len(html)} bytes)")
    except Exception as exc:
        print(f"failed {url}: {exc}")


async def main():
    raw = input("Enter LinkedIn profile URL: ").strip()
    slug, base = normalize_profile(raw)

    out_dir = Path("dom_dumps") / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    async with BrowserManager(headless=False) as browser:
        await browser.load_session("linkedin_session.json")
        for label, sub in SUBPATHS.items():
            await dump_url(browser.page, base + sub, out_dir / f"{label}.html")


if __name__ == "__main__":
    asyncio.run(main())
