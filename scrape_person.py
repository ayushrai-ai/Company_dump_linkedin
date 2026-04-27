import asyncio
import json
import re
from pathlib import Path

from company_scraper.browser import BrowserManager
from company_scraper.person import PersonScraper

_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name or "person")
    return re.sub(r"[\s-]+", "_", name).strip("_")[:80]


async def main():
    url = input("Enter LinkedIn profile URL: ").strip()
    m = _RE.search(url)
    if not m:
        raise ValueError("Not a valid LinkedIn profile URL.")
    url = f"https://www.linkedin.com/in/{m.group(1).strip('/')}/"

    async with BrowserManager(headless=False) as browser:
        await browser.load_session("linkedin_session.json")
        person = await PersonScraper(browser.page).scrape(url)

    out = Path("output")
    out.mkdir(exist_ok=True)
    fname = _safe_filename(person.name or m.group(1))
    path = out / f"{fname}.json"
    path.write_text(json.dumps(person.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {path}")


if __name__ == "__main__":
    asyncio.run(main())
