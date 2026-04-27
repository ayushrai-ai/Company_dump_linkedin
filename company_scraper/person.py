
from __future__ import annotations

import logging
import re
from typing import List, Optional

from playwright.async_api import Page

from .base import BaseScraper
from .exceptions import ScraperError
from .models import Accomplishment, Contact, Education, Experience, Person, PersonPost

logger = logging.getLogger(__name__)

_MIDDOT_RE = re.compile(r"[··]")
_MORE_SUFFIX_RE = re.compile(r"[…\.]{1,3}\s*more\s*$", re.IGNORECASE)


def _clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = text.replace(" ", " ").strip()
    cleaned = _MORE_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned


class PersonScraper(BaseScraper):
    """Async scraper for LinkedIn person profiles."""

    def __init__(self, page: Page):
        super().__init__(page)

    async def scrape(self, linkedin_url: str) -> Person:
        logger.info("Navigating to profile: %s", linkedin_url)

        try:
            await self.navigate_and_wait(linkedin_url)
            await self.ensure_logged_in()
            await self.page.wait_for_selector("main", timeout=10000)
            await self.human_browse_noise()

            await self.scroll_page_to_half()
            await self.human_pause(500, 1400)
            await self.scroll_page_to_bottom(pause_time=0.6, max_scrolls=3)
            await self.human_browse_noise()

            name = await self._get_name()
            location = await self._get_location()
            open_to_work = await self._check_open_to_work()
            headline = await self._get_headline(name)
            followers = await self._get_followers()
            about = await self._get_about()
            logger.info("Got name: %s", name)

            experiences = await self._get_experiences(linkedin_url)
            logger.info("Got %d experiences", len(experiences))
            await self.human_browse_noise()

            educations = await self._get_educations(linkedin_url)
            logger.info("Got %d educations", len(educations))
            await self.human_browse_noise()

            honors = await self._get_honors(linkedin_url)
            logger.info("Got %d honors", len(honors))
            await self.human_browse_noise()

            contacts = await self._get_contacts(linkedin_url)
            logger.info("Got %d contacts", len(contacts))

            posts = await self._get_posts(linkedin_url)
            logger.info("Got %d posts", len(posts))

            return Person(
                linkedin_url=linkedin_url,
                name=name,
                location=location,
                open_to_work=open_to_work,
                headline=headline,
                followers=followers,
                about=about,
                experiences=experiences,
                educations=educations,
                accomplishments=honors,
                contacts=contacts,
                posts=posts,
            )

        except Exception as e:
            raise ScraperError(f"Failed to scrape person profile: {e}") from e

    #  header fields 

    async def _get_name(self) -> Optional[str]:

        try:
            title = await self.page.title()
        except Exception:
            title = ""

        if title:
            cleaned = re.sub(r"^\(\d+\)\s*", "", title) 
            cleaned = cleaned.split(" | LinkedIn")[0].split(" - LinkedIn")[0].strip()
            if cleaned and cleaned.lower() != "linkedin":
                return cleaned

        # Fallback: first h1 or h2 in main.
        for sel in ("main h1", "main h2"):
            txt = _clean_text(await self.safe_extract_text(sel))
            if txt:
                return txt
        return None

    async def _get_location(self) -> Optional[str]:
        try:
            contact_link = self.page.locator(
                'main a[href*="/overlay/contact-info"]'
            ).first
            if await contact_link.count() == 0:
                return None
            parent = contact_link.locator("xpath=ancestor::div[1]")
            ps = await parent.locator("p").all()
            for p in ps:
                text = _clean_text(await p.text_content())
                if not text or _MIDDOT_RE.fullmatch(text):
                    continue
                if "contact info" in text.lower():
                    continue
                return text
        except Exception as exc:
            logger.debug("location extraction failed: %s", exc)
        return None

    async def _get_headline(self, name: Optional[str]) -> Optional[str]:
        try:
            if not name:
                return None
            safe = name.replace('"', "'")
            el = self.page.locator(
                f'xpath=//main//p[normalize-space()="{safe}"]/following-sibling::div[1]//p[1]'
            ).first
            if await el.count() > 0:
                return _clean_text(await el.text_content()) or None
        except Exception as exc:
            logger.debug("headline extraction failed: %s", exc)
        return None

    async def _get_followers(self) -> Optional[str]:
        try:
            el = self.page.locator("main p").filter(
                has_text=re.compile(r"\d.*followers", re.IGNORECASE)
            ).first
            if await el.count() > 0:
                text = _clean_text(await el.text_content())
                m = re.search(r"([\d,]+)\s*followers", text, re.IGNORECASE)
                if m:
                    return m.group(1)
        except Exception as exc:
            logger.debug("followers extraction failed: %s", exc)
        return None

    async def _check_open_to_work(self) -> bool:
        try:
            imgs = await self.page.locator("main img[title]").all()
            for img in imgs[:10]:
                title = (await img.get_attribute("title")) or ""
                if "OPEN_TO_WORK" in title.upper():
                    return True
        except Exception:
            pass
        return False

    #  experience 

    async def _get_experiences(self, base_url: str) -> List[Experience]:
        url = base_url.rstrip("/") + "/details/experience/"
        experiences: List[Experience] = []

        try:
            await self.navigate_and_wait(url)
            await self.page.wait_for_selector("main", timeout=10000)
            await self.human_browse_noise()
            await self.scroll_page_to_bottom(pause_time=0.6, max_scrolls=4)
        except Exception as exc:
            logger.warning("Could not open experience page: %s", exc)
            return experiences

        items = await self._collect_entity_items()
        for item in items:
            try:
                exp = await self._parse_experience_item(item)
                if exp:
                    experiences.append(exp)
            except Exception as exc:
                logger.debug("exp parse error: %s", exc)
        return experiences

    async def _parse_experience_item(self, item) -> Optional[Experience]:
        texts = await self._collect_item_p_texts(item)
        if not texts:
            return None

        company_url = await self._first_linkedin_entity_url(
            item, ("/company/", "/school/")
        )

        position_title = texts[0] if len(texts) > 0 else None
        company_raw = texts[1] if len(texts) > 1 else None
        dates = texts[2] if len(texts) > 2 else None
        location = texts[3] if len(texts) > 3 else None

        company_name = None
        if company_raw:
            parts = _MIDDOT_RE.split(company_raw)
            company_name = parts[0].strip() if parts else company_raw

        from_date, to_date, duration = self._parse_work_times(dates or "")
        description = await self._get_expandable_text(item)

        if not (position_title or company_name):
            return None

        return Experience(
            position_title=position_title,
            institution_name=company_name,
            linkedin_url=company_url,
            from_date=from_date,
            to_date=to_date,
            duration=duration,
            location=location,
            description=description,
        )

    def _parse_work_times(
        self, work_times: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if not work_times:
            return None, None, None
        try:
            parts = _MIDDOT_RE.split(work_times)
            times = parts[0].strip() if parts else ""
            duration = parts[1].strip() if len(parts) > 1 else None

            # Dash may be hyphen-minus, en-dash, or em-dash.
            date_parts = re.split(r"\s[-–—]\s", times, maxsplit=1)
            from_date = date_parts[0].strip() if date_parts else ""
            to_date = date_parts[1].strip() if len(date_parts) > 1 else ""
            return from_date or None, to_date or None, duration
        except Exception as exc:
            logger.debug("parse_work_times error: %s", exc)
            return None, None, None

    #  education 

    async def _get_educations(self, base_url: str) -> List[Education]:
        url = base_url.rstrip("/") + "/details/education/"
        educations: List[Education] = []

        try:
            await self.navigate_and_wait(url)
            await self.page.wait_for_selector("main", timeout=10000)
            await self.human_browse_noise()
            await self.scroll_page_to_bottom(pause_time=0.6, max_scrolls=4)
        except Exception as exc:
            logger.warning("Could not open education page: %s", exc)
            return educations

        items = await self._collect_entity_items()
        for item in items:
            try:
                edu = await self._parse_education_item(item)
                if edu:
                    educations.append(edu)
            except Exception as exc:
                logger.debug("edu parse error: %s", exc)
        return educations

    async def _parse_education_item(self, item) -> Optional[Education]:
        texts = await self._collect_item_p_texts(item)
        if not texts:
            return None

        institution_url = await self._first_linkedin_entity_url(
            item, ("/school/", "/company/")
        )

        institution_name = texts[0]
        degree: Optional[str] = None
        times: str = ""

        if len(texts) >= 3:
            degree = texts[1]
            times = texts[2]
        elif len(texts) == 2:
            second = texts[1]
            if any(ch.isdigit() for ch in second) or " - " in second:
                times = second
            else:
                degree = second

        from_date, to_date = self._parse_year_range(times)
        description = await self._get_expandable_text(item)

        return Education(
            institution_name=institution_name or None,
            degree=degree or None,
            linkedin_url=institution_url,
            from_date=from_date,
            to_date=to_date,
            description=description,
        )

    def _parse_year_range(self, times: str) -> tuple[Optional[str], Optional[str]]:
        if not times:
            return None, None
        parts = re.split(r"\s[-–—]\s", times, maxsplit=1)
        from_date = parts[0].strip() if parts else ""
        to_date = parts[1].strip() if len(parts) > 1 else from_date
        return from_date or None, to_date or None

    #  contacts 

    async def _get_contacts(self, base_url: str) -> List[Contact]:
        url = base_url.rstrip("/") + "/overlay/contact-info/"
        contacts: List[Contact] = []
        try:
            await self.navigate_and_wait(url)
            await self.human_pause(800, 1800)
        except Exception as exc:
            logger.warning("Could not open contact-info overlay: %s", exc)
            return contacts

        dialog = self.page.locator('dialog, [role="dialog"]').first
        try:
            if await dialog.count() == 0:
                return contacts
        except Exception:
            return contacts

        try:
            sections = await dialog.locator("section, h3").all()
        except Exception:
            sections = []

        try:
            anchors = await dialog.locator("a[href]").all()
        except Exception:
            anchors = []

        for anchor in anchors:
            try:
                href = await anchor.get_attribute("href") or ""
                text = _clean_text(await anchor.text_content())
            except Exception:
                continue
            if not href:
                continue

            if href.startswith("mailto:"):
                contacts.append(Contact(type="email", value=href.replace("mailto:", "")))
            elif href.startswith("tel:"):
                contacts.append(Contact(type="phone", value=href.replace("tel:", "")))
            elif "linkedin.com/in/" in href:
                contacts.append(Contact(type="linkedin", value=href.split("?")[0]))
            elif "twitter.com" in href or "x.com" in href:
                contacts.append(Contact(type="twitter", value=href, label=text or None))
            elif href.startswith("http") and "linkedin.com" not in href:
                contacts.append(Contact(type="website", value=href, label=text or None))

        # Dedup.
        seen: set[tuple[str, str]] = set()
        unique: List[Contact] = []
        for c in contacts:
            key = (c.type, c.value)
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)

        
        _ = sections
        return unique

    #  about 

    async def _get_about(self) -> Optional[str]:
        try:
            about_section = self.page.locator(
                'main section'
            ).filter(has=self.page.locator('h2:text("About")'))
            if await about_section.count() == 0:
                return None
            span = about_section.locator('[data-testid="expandable-text-box"]').first
            if await span.count() > 0:
                return _clean_text(await span.text_content()) or None
            # fallback: largest <span> in section
            spans = await about_section.locator('span').all()
            best = ""
            for s in spans:
                t = _clean_text(await s.text_content())
                if len(t) > len(best):
                    best = t
            return best or None
        except Exception as exc:
            logger.debug("about extraction failed: %s", exc)
        return None

    #  honors 

    async def _get_honors(self, base_url: str) -> List[Accomplishment]:
        url = base_url.rstrip("/") + "/details/honors/"
        honors: List[Accomplishment] = []
        try:
            await self.navigate_and_wait(url)
            await self.page.wait_for_selector("main", timeout=10000)
            await self.human_browse_noise()
            await self.scroll_page_to_bottom(pause_time=0.6, max_scrolls=4)
        except Exception as exc:
            logger.warning("Could not open honors page: %s", exc)
            return honors

        items = await self._collect_entity_items()
        for item in items:
            try:
                texts = await self._collect_item_p_texts(item)
                if not texts:
                    continue
                honors.append(Accomplishment(
                    category="honor",
                    title=texts[0],
                    issuer=texts[1] if len(texts) > 1 else None,
                    issued_date=texts[2] if len(texts) > 2 else None,
                ))
            except Exception as exc:
                logger.debug("honor parse error: %s", exc)
        return honors

    #  posts 

    async def _get_posts(self, base_url: str) -> List[PersonPost]:
        url = base_url.rstrip("/") + "/recent-activity/all/"
        posts: List[PersonPost] = []
        try:
            await self.navigate_and_wait(url)
            await self.page.wait_for_selector(
                'ul.display-flex.flex-wrap.list-style-none.justify-center',
                timeout=15000,
            )
            await self.human_browse_noise()
        except Exception as exc:
            logger.warning("Could not open activity page: %s", exc)
            return posts

        ul = self.page.locator(
            'ul.display-flex.flex-wrap.list-style-none.justify-center'
        ).first
        if await ul.count() == 0:
            return posts

        lis = await ul.locator('li').all()
        for li in lis:
            try:
                text_el = li.locator('[class*="__commentary"]').first
                text = ""
                if await text_el.count() > 0:
                    text = _clean_text(await text_el.text_content())

                time_el = li.locator('[class*="actor__sub-description"]').first
                posted_at = ""
                if await time_el.count() > 0:
                    raw = _clean_text(await time_el.text_content())
                    posted_at = raw.split("•")[0].strip()

                if text:
                    posts.append(PersonPost(content=text, posted_at=posted_at or None))
                    if len(posts) >= 3:
                        break
            except Exception as exc:
                logger.debug("post parse error: %s", exc)
        return posts

    #  generic helpers 

    async def _collect_entity_items(self) -> list:
        """Find all `div[componentkey^="entity-collection-item"]` items in main."""
        try:
            items = await self.page.locator(
                'main div[componentkey^="entity-collection-item"]'
            ).all()
            return items
        except Exception:
            return []

    async def _collect_item_p_texts(self, item) -> List[str]:
        """Collect the visible <p> texts inside an entity item, dedup in order."""
        out: List[str] = []
        seen: set[str] = set()
        try:
            ps = await item.locator("p").all()
        except Exception:
            return out

        for p in ps:
            try:
                text = _clean_text(await p.text_content())
            except Exception:
                continue
            if not text or _MIDDOT_RE.fullmatch(text) or len(text) > 300:
                continue
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
        return out

    async def _first_linkedin_entity_url(
        self, item, href_prefixes: tuple[str, ...]
    ) -> Optional[str]:
        """Return the first `<a href>` inside `item` whose href contains any prefix."""
        try:
            anchors = await item.locator("a[href]").all()
        except Exception:
            return None
        for anchor in anchors:
            try:
                href = await anchor.get_attribute("href")
            except Exception:
                continue
            if not href:
                continue
            for prefix in href_prefixes:
                if prefix in href:
                    return href.split("?")[0]
        return None

    async def _get_expandable_text(self, item) -> Optional[str]:
        try:
            span = item.locator('span[data-testid="expandable-text-box"]').first
            if await span.count() == 0:
                return None
            text = _clean_text(await span.text_content())
            return text or None
        except Exception:
            return None
