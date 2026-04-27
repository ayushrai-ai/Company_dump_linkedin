import asyncio
import json
import logging
import re
from pathlib import Path

from company_scraper.browser import BrowserManager
from company_scraper.company import CompanyScraper
from company_scraper.models import Company, Person
from company_scraper.person import PersonScraper

logging.basicConfig(level=logging.INFO)

COMPANY_URL_RE = re.compile(
    r"^(?:https?://)?(?:[a-z0-9-]+\.)?linkedin\.com/company/([^/?#]+)",
    flags=re.IGNORECASE,
)

PROFILE_URL_RE = re.compile(
    r"^(?:https?://)?(?:[a-z0-9-]+\.)?linkedin\.com/in/([^/?#]+)",
    flags=re.IGNORECASE,
)


def company_name_from_url(linkedin_url: str) -> str:
    """Extract a stable company slug from LinkedIn URL as name fallback."""
    m = COMPANY_URL_RE.search(linkedin_url or "")
    if not m:
        return ""
    slug = m.group(1).strip()
    return slug.replace("-", " ")


def safe_filename(name: str, max_len: int = 80) -> str:
    """
    Convert company name to a filesystem-safe filename.
    Example: "AT&T, Inc." -> "AT_T_Inc"
    """
    name = (name or "").strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s-]+", "_", name)
    name = name.strip("_")
    return (name[:max_len] or "company")


def normalize_company_url(raw_url: str, section: str = "about") -> str:
    """
    Accept a LinkedIn company URL in any common form and return the canonical
    `https://www.linkedin.com/company/<slug>/<section>/` form.
    """
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("Please enter a LinkedIn company URL.")

    m = COMPANY_URL_RE.search(url)
    if not m:
        raise ValueError(
            "URL does not look like a LinkedIn company page "
            "(expected linkedin.com/company/<slug>)."
        )

    slug = m.group(1).strip().strip("/")
    sec = (section or "about").strip("/").lower()
    return f"https://www.linkedin.com/company/{slug}/{sec}/"


def normalize_profile_url(raw_url: str) -> str:
    """Normalize a LinkedIn profile URL to `https://www.linkedin.com/in/<slug>/`."""
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("Please enter a LinkedIn profile URL.")

    m = PROFILE_URL_RE.search(url)
    if not m:
        raise ValueError(
            "URL does not look like a LinkedIn profile "
            "(expected linkedin.com/in/<slug>)."
        )
    slug = m.group(1).strip().strip("/")
    return f"https://www.linkedin.com/in/{slug}/"


def has_useful_company_data(company: Company) -> bool:
    """Treat scrape as successful only if at least one meaningful field is present."""
    return any([
        company.name,
        company.tagline,
        company.description,
        company.website,
        company.industry,
        company.company_size,
    ])


def save_json(obj_dict: dict, out_dir: Path, filename: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{filename}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj_dict, f, ensure_ascii=False, indent=2)
    return path


async def scrape_founder(
    page,
) -> tuple[Person, str] | None:
    manual = input(
        "Paste the founder's LinkedIn profile URL (or press Enter to skip): "
    ).strip()
    if not manual:
        return None
    try:
        founder_url = normalize_profile_url(manual)
    except ValueError as exc:
        print(f"✗ {exc}")
        return None

    person_scraper = PersonScraper(page)
    print(f"Scraping founder profile: {founder_url}")
    try:
        person = await person_scraper.scrape(founder_url)
    except Exception as exc:
        logging.warning("Failed to scrape founder profile %s: %s", founder_url, exc)
        return None

    return person, founder_url


async def main():
    input_url = input("Enter LinkedIn company URL: ").strip()
    company_url = normalize_company_url(input_url, section="about")

    session_file = "linkedin_session.json"  # created by create_session.py
    out_dir = Path("output")

    async with BrowserManager(headless=False) as browser:
        await browser.load_session(session_file)

        scraper = CompanyScraper(browser.page)

        print(f"Scraping: {company_url}")
        try:
            company = await scraper.scrape(company_url)
        except Exception as exc:
            raise RuntimeError(f"Failed to scrape {company_url}: {exc}") from exc

        if not has_useful_company_data(company):
            raise RuntimeError(f"No useful data found at {company_url}.")

        company_name = (
            company.name or company_name_from_url(company.linkedin_url) or "company"
        )
        safe_name = safe_filename(company_name)

        company_path = save_json(company.to_dict(), out_dir, safe_name)
        print(f"✓ Scraped company: {company_name}")
        print(f"✓ Saved to: {company_path}")

        people = await scraper.get_people(company_url)
        people_path = save_json(
            [p.model_dump() for p in people],
            out_dir,
            f"{safe_name}__people",
        )
        print(f"✓ Scraped {len(people)} people → {people_path}")

        founder_result = await scrape_founder(browser.page)
        if founder_result is None:
            print("⚠ Skipped founder scrape.")
            return

        person, founder_url = founder_result
        person_name = person.name or "founder"
        founder_path = save_json(
            person.to_dict(),
            out_dir,
            f"{safe_name}__founder_{safe_filename(person_name)}",
        )
        print(f"✓ Scraped founder: {person_name} ({founder_url})")
        print(f"✓ Saved to: {founder_path}")


if __name__ == "__main__":
    asyncio.run(main())