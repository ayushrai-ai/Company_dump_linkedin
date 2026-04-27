from __future__ import annotations

import logging
import random
import re
from typing import Optional, Dict, Any, List

from playwright.async_api import Page

from .models import Company, CompanyPost
from .exceptions import AuthenticationError
from .utils import detect_rate_limit, is_logged_in, extract_text_safe

logger = logging.getLogger(__name__)


class CompanyScraper:

    def __init__(self, page: Page):
        self.page = page

    async def scrape(self, linkedin_url: str, timeout_ms: int = 60000) -> Company:
        logger.info("Navigating to company page: %s", linkedin_url)
        await self.page.goto(linkedin_url, wait_until="domcontentloaded", timeout=timeout_ms)
        await self._human_pause(700, 1700)

        await detect_rate_limit(self.page)

        if not await is_logged_in(self.page):
            raise AuthenticationError("Not logged in. Load a valid LinkedIn session before scraping.")

        await detect_rate_limit(self.page)
        await self._human_browse_noise(linkedin_url, return_url=linkedin_url)

        # Basic
        name = await self._get_name()
        tagline = await self._get_tagline_best_effort()
        about = await self._get_about()

        # Overview / about fields
        overview = await self._get_overview_best_effort()
        posts = await self._get_posts_best_effort(linkedin_url, limit=5, timeout_ms=timeout_ms)

        return Company(
            linkedin_url=linkedin_url,
            name=name,
            tagline=tagline,
            description=overview.get("description") or about,
            website=overview.get("website"),
            phone=overview.get("phone"),
            headquarters=overview.get("headquarters"),
            founded=overview.get("founded"),
            industry=overview.get("industry"),
            company_type=overview.get("company_type"),
            company_size=overview.get("company_size"),
            specialties=overview.get("specialties"),
            posts=posts,
            extra=overview.get("extra", {}),
        )

    async def _get_name(self) -> Optional[str]:
        name = await extract_text_safe(self.page, "h1", default="")
        return name or None

    async def _get_about(self) -> Optional[str]:
        # Trying multiple patterns
        candidates = [
            # Current Preferred: LinkedIn overview paragraph block from current UI
            "p.break-words.white-space-pre-wrap.t-black--light.text-body-medium",
            'section:has(h2:has-text("About")) p',
            'section:has(h2:has-text("About us")) p',
            'main section:has-text("About") p',
            # fallback: any long div text block
            'section:has(h2:has-text("About")) div',
        ]
        best = ""
        for sel in candidates:
            txt = await extract_text_safe(self.page, sel, default="")
            if len(txt) > len(best):
                best = txt

        if len(best) < 30:
            # API payload fallback embedded in page HTML
            try:
                html = await self.page.content()
                m = re.search(r'"description":"([^"\\]*(?:\\.[^"\\]*)*)"', html)
                if m:
                    payload_text = bytes(m.group(1), "utf-8").decode("unicode_escape").strip()
                    if len(payload_text) > len(best):
                        best = payload_text
            except Exception:
                pass

        return best if len(best) >= 30 else None

    async def _get_tagline_best_effort(self) -> Optional[str]:
        candidates = [
            "h4.org-top-card-summary__tagline",
            "p.org-top-card-summary__tagline",
            "div.org-top-card-summary__tagline",
            'section:has(h2:has-text("Overview")) h4',
            'main h4:has-text("Meet")',
        ]

        best = ""
        for sel in candidates:
            txt = await extract_text_safe(self.page, sel, default="")
            if len(txt) > len(best):
                best = txt

        if len(best) < 20:
            # Fallback to LinkedIn embedded state data in the page HTML.
            try:
                html = await self.page.content()
                m = re.search(r'"tagline":"([^"\\]*(?:\\.[^"\\]*)*)"', html)
                if m:
                    payload_text = bytes(m.group(1), "utf-8").decode("unicode_escape").strip()
                    if len(payload_text) > len(best):
                        best = payload_text
            except Exception:
                pass

        return best if len(best) >= 20 else None

    async def _get_overview_best_effort(self) -> Dict[str, Any]:
        overview: Dict[str, Any] = {
            "description": None,
            "website": None,
            "phone": None,
            "headquarters": None,
            "founded": None,
            "industry": None,
            "company_type": None,
            "company_size": None,
            "specialties": None,
            "extra": {},
        }

        # 1) Try old dt/dd (keep it)
        try:
            dts = await self.page.locator("dt").all()
            for dt in dts:
                label = (await dt.inner_text()).strip().lower()
                dd = dt.locator("xpath=following-sibling::dd[1]")
                if await dd.count() == 0:
                    continue
                value = (await dd.inner_text()).strip()
                if not value:
                    continue

                if "website" in label:
                    overview["website"] = overview["website"] or value
                elif "phone" in label:
                    overview["phone"] = overview["phone"] or self._clean_phone(value)
                elif "description" in label or "overview" in label:
                    overview["description"] = overview["description"] or value
                elif "headquarters" in label or "location" in label:
                    overview["headquarters"] = overview["headquarters"] or value
                elif "founded" in label:
                    overview["founded"] = overview["founded"] or value
                elif "industry" in label:
                    overview["industry"] = overview["industry"] or value
                elif "company type" in label or label == "type":
                    overview["company_type"] = overview["company_type"] or value
                elif "company size" in label or label == "size":
                    overview["company_size"] = overview["company_size"] or value
                elif "specialt" in label:
                    overview["specialties"] = overview["specialties"] or value
        except Exception:
            pass

        # 2) Newer About pages: label/value in list items (best-effort)
        # Grab all list items under main, then parse lines like:
        # "Website\nhttps://...\nIndustry\nSoftware Development\n..."
        if not any(overview[k] for k in ["website", "industry", "company_size", "headquarters", "founded"]):
            try:
                items = await self.page.locator("main li").all()
                for li in items:
                    text = (await li.inner_text()).strip()
                    if not text:
                        continue

                    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                    if len(lines) < 2:
                        continue

                    # Common pattern: first line is label, second line is value
                    label = lines[0].lower()
                    value = lines[1]

                    if label in ("website",):
                        overview["website"] = overview["website"] or value
                    elif label in ("phone",):
                        overview["phone"] = overview["phone"] or self._clean_phone(value)
                    elif label in ("description", "overview"):
                        overview["description"] = overview["description"] or value
                    elif label in ("headquarters", "head office", "location"):
                        overview["headquarters"] = overview["headquarters"] or value
                    elif label in ("founded",):
                        overview["founded"] = overview["founded"] or value
                    elif label in ("industry",):
                        overview["industry"] = overview["industry"] or value
                    elif label in ("company size", "size"):
                        overview["company_size"] = overview["company_size"] or value
                    elif label in ("type", "company type"):
                        overview["company_type"] = overview["company_type"] or value
                    elif "specialt" in label:
                        overview["specialties"] = overview["specialties"] or value

                    # Followers sometimes appear as an unlabeled line
                    for ln in lines:
                        if "follower" in ln.lower() and "followers" not in (overview["extra"].get("followers") or "").lower():
                            overview["extra"]["followers"] = ln
            except Exception:
                pass

        # 3) External website fallback (keep it)
        if not overview["website"]:
            overview["website"] = await self._find_external_website()

        # Fallback to direct extraction of the overview paragraph text block.
        if not overview["description"]:
            overview["description"] = await extract_text_safe(
                self.page,
                "p.break-words.white-space-pre-wrap.t-black--light.text-body-medium",
                default="",
            ) or None

        if not overview["description"]:
            overview["description"] = await self._get_about()

        return overview

    async def _get_posts_best_effort(self, linkedin_url: str, limit: int = 5, timeout_ms: int = 60000) -> List[CompanyPost]:
        posts_url = self._to_posts_url(linkedin_url)
        logger.info("Navigating to company posts page: %s", posts_url)

        try:
            await self.page.goto(posts_url, wait_until="domcontentloaded", timeout=timeout_ms)
            await self._human_pause(800, 1800)
            await detect_rate_limit(self.page)
            await self._human_browse_noise(linkedin_url, return_url=posts_url)
        except Exception as exc:
            logger.warning("Could not open posts page %s: %s", posts_url, exc)
            return []

        posts = await self._extract_posts_from_dom(limit)
        if len(posts) >= limit:
            return posts[:limit]

        # Fallback: parse update payload embedded in the rendered HTML when DOM selectors miss posts.
        try:
            html = await self.page.content()
            fallback_posts = self._extract_posts_from_payload(html, limit)
            seen = {self._post_identity(p) for p in posts}
            for post in fallback_posts:
                key = self._post_identity(post)
                if key in seen:
                    continue
                posts.append(post)
                seen.add(key)
                if len(posts) >= limit:
                    break
        except Exception:
            pass

        return posts[:limit]

    async def _extract_posts_from_dom(self, limit: int) -> List[CompanyPost]:
        posts: List[CompanyPost] = []
        seen: set[str] = set()

        card_selectors = [
            "div.feed-shared-update-v2",
            "main div[data-urn^='urn:li:activity:']",
            "main div[data-id^='urn:li:activity:']",
        ]

        cards_locator = None
        for sel in card_selectors:
            loc = self.page.locator(sel)
            if await loc.count() > 0:
                cards_locator = loc
                break

        if cards_locator is None:
            cards_locator = self.page.locator("main article, main li")

        for _ in range(7):
            total = await cards_locator.count()
            inspect_count = min(total, max(limit * 3, 12))
            for idx in range(inspect_count):
                card = cards_locator.nth(idx)
                post = await self._extract_single_post_from_card(card)
                if post is None:
                    continue
                key = self._post_identity(post)
                if key in seen:
                    continue
                seen.add(key)
                posts.append(post)
                if len(posts) >= limit:
                    return posts[:limit]

            await self.page.mouse.wheel(0, 2500)
            await self.page.wait_for_timeout(1200)

        return posts[:limit]

    async def _extract_single_post_from_card(self, card: Any) -> Optional[CompanyPost]:
        text_selectors = [
            ".update-components-text .break-words",
            ".update-components-text",
            "span.break-words",
            "div.feed-shared-text",
        ]
        content = await self._extract_text_from_card(card, text_selectors)

        time_selectors = [
            ".update-components-actor__sub-description span[aria-hidden='true']",
            "span.update-components-actor__sub-description",
            "time",
        ]
        posted_at = await self._extract_text_from_card(card, time_selectors)

        likes = None
        likes_text_selectors = [
            ".social-details-social-counts__reactions-count",
            ".social-details-social-counts__social-proof-text",
        ]
        likes_text = await self._extract_text_from_card(card, likes_text_selectors)
        if likes_text:
            likes = self._parse_count(likes_text)

        comments = None
        comments_text_selectors = [
            ".social-details-social-counts__comments",
            "a[data-test-id='social-actions__comments']",
        ]
        comments_text = await self._extract_text_from_card(card, comments_text_selectors)
        if comments_text:
            comments = self._parse_count(comments_text)

        if comments is None:
            buttons = card.locator("button[aria-label*='comment' i], a[aria-label*='comment' i]")
            btn_count = await buttons.count()
            for i in range(min(btn_count, 6)):
                label = await buttons.nth(i).get_attribute("aria-label")
                comments = self._parse_count(label or "")
                if comments is not None:
                    break

        if not any([content, posted_at, likes is not None, comments is not None]):
            return None

        return CompanyPost(
            posted_at=(posted_at or None),
            content=(content or None),
            likes=likes,
            comments=comments,
        )

    async def _extract_text_from_card(self, card: Any, selectors: List[str]) -> str:
        best = ""
        for sel in selectors:
            try:
                loc = card.locator(sel).first
                if await loc.count() == 0:
                    continue
                txt = (await loc.inner_text()).strip()
                if len(txt) > len(best):
                    best = txt
            except Exception:
                continue
        return best

    def _extract_posts_from_payload(self, html: str, limit: int) -> List[CompanyPost]:
        posts: List[CompanyPost] = []
        counts_by_id: Dict[str, Dict[str, Optional[int]]] = {}

        count_blocks = re.finditer(
            r'"\$type":"com\.linkedin\.voyager\.dash\.feed\.SocialActivityCounts".{0,900}?\}',
            html,
            flags=re.DOTALL,
        )
        for block_match in count_blocks:
            block = block_match.group(0)
            urn_match = re.search(r'"urn":"(urn:li:(?:activity|ugcPost):\d+)"', block)
            if not urn_match:
                continue
            id_match = re.search(r':(\d+)$', urn_match.group(1))
            if not id_match:
                continue

            likes_match = re.search(r'"numLikes":(\d+)', block)
            comments_match = re.search(r'"numComments":(\d+)', block)
            counts_by_id[id_match.group(1)] = {
                "likes": int(likes_match.group(1)) if likes_match else None,
                "comments": int(comments_match.group(1)) if comments_match else None,
            }

        text_blocks = re.finditer(
            r'"backendUrn":"(urn:li:activity:\d+)".{0,8000}?"commentary":\{.{0,8000}?"text":\{[^{}]*?"text":"((?:[^"\\]|\\.)*)"',
            html,
            flags=re.DOTALL,
        )

        seen: set[str] = set()
        for match in text_blocks:
            backend_urn = match.group(1)
            text_raw = match.group(2)
            id_match = re.search(r':(\d+)$', backend_urn)
            if not id_match:
                continue
            activity_id = id_match.group(1)
            if activity_id in seen:
                continue

            text = self._decode_json_text(text_raw)
            if len(text) < 8:
                continue

            counts = counts_by_id.get(activity_id, {})
            posts.append(
                CompanyPost(
                    posted_at=None,
                    content=text,
                    likes=counts.get("likes"),
                    comments=counts.get("comments"),
                )
            )
            seen.add(activity_id)
            if len(posts) >= limit:
                break

        return posts[:limit]

    def _decode_json_text(self, value: str) -> str:
        try:
            decoded = bytes(value, "utf-8").decode("unicode_escape")
            return decoded.strip()
        except Exception:
            return (value or "").replace("\\n", "\n").replace('\\"', '"').strip()

    def _parse_count(self, text: str) -> Optional[int]:
        if not text:
            return None
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*([kKmM]?)", text)
        if not m:
            return None

        number_str = m.group(1).replace(",", "")
        suffix = (m.group(2) or "").lower()
        try:
            value = float(number_str)
        except ValueError:
            return None

        if suffix == "k":
            value *= 1000
        elif suffix == "m":
            value *= 1_000_000

        return int(value)

    def _to_posts_url(self, linkedin_url: str) -> str:
        base = (linkedin_url or "").strip()
        if "/about/" in base:
            return base.replace("/about/", "/posts/", 1)
        if base.rstrip("/").endswith("/about"):
            return base.rstrip("/")[:-6] + "/posts/"
        return base.rstrip("/") + "/posts/"

    def _to_people_url(self, linkedin_url: str, keywords: Optional[str] = None) -> str:
        """Build the company's /people/ URL, optionally with a keyword filter."""
        base = (linkedin_url or "").strip()
        m = re.search(
            r"(https?://www\.linkedin\.com/company/[^/?#]+)",
            base,
            flags=re.IGNORECASE,
        )
        root = m.group(1) if m else base.rstrip("/").split("?")[0]
        url = f"{root.rstrip('/')}/people/"
        if keywords:
            url += f"?keywords={keywords}"
        return url

    async def find_founder_url(
        self,
        linkedin_url: str,
        timeout_ms: int = 60000,
    ) -> Optional[str]:
        """
        Search the company's /people/ tab for someone whose title matches
        founder/CEO patterns and return their profile URL (None if not found).
        """
        founder_re = re.compile(
            r"\b(co[-\s]?founder|founding\s+\w+|founder|chief\s+executive(?:\s+officer)?|\bceo\b)\b",
            flags=re.IGNORECASE,
        )

        # Try the keyword-filtered people page first, then the plain /people/ as fallback.
        candidate_urls = [
            self._to_people_url(linkedin_url, keywords="founder"),
            self._to_people_url(linkedin_url, keywords="ceo"),
            self._to_people_url(linkedin_url),
        ]

        for people_url in candidate_urls:
            logger.info("Looking for founder at: %s", people_url)
            try:
                await self.page.goto(
                    people_url, wait_until="domcontentloaded", timeout=timeout_ms
                )
                await self._human_pause(800, 1800)
                await detect_rate_limit(self.page)
            except Exception as exc:
                logger.warning("Could not open %s: %s", people_url, exc)
                continue

            # Nudge the page to render lazy-loaded results.
            try:
                await self.page.mouse.wheel(0, 1500)
                await self._human_pause(500, 1000)
                await self.page.mouse.wheel(0, 1500)
                await self._human_pause(500, 1000)
            except Exception:
                pass

            card_selectors = [
                "div.org-people-profile-card",
                "ul.org-people-profiles-module__profile-list > li",
                "main ul li:has(a[href*='/in/'])",
            ]

            cards: list = []
            for sel in card_selectors:
                loc = self.page.locator(sel)
                try:
                    count = await loc.count()
                except Exception:
                    count = 0
                if count > 0:
                    cards = await loc.all()
                    break

            if not cards:
                continue

            for card in cards:
                try:
                    text = (await card.inner_text()).strip()
                except Exception:
                    continue
                if not text or not founder_re.search(text):
                    continue

                link = card.locator('a[href*="/in/"]').first
                try:
                    if await link.count() == 0:
                        continue
                    href = await link.get_attribute("href")
                except Exception:
                    continue
                if not href:
                    continue

                # Normalize to a clean profile URL (no query / overlays).
                profile_url = href.split("?")[0].split("#")[0].rstrip("/")
                if "/in/" not in profile_url:
                    continue
                logger.info("Found candidate founder: %s", profile_url)
                return profile_url + "/"

        return None

    def _post_identity(self, post: CompanyPost) -> str:
        content_key = (post.content or "")[:120].strip().lower()
        posted_key = (post.posted_at or "").strip().lower()
        return f"{posted_key}|{content_key}"

    def _clean_phone(self, raw_value: str) -> str:
        # Keep only the first visible phone line when LinkedIn duplicates helper text.
        if not raw_value:
            return raw_value
        first_line = raw_value.splitlines()[0].strip()
        return first_line or raw_value.strip()

    async def _human_pause(self, min_ms: int = 400, max_ms: int = 1200) -> None:
        wait_ms = random.randint(min_ms, max_ms)
        await self.page.wait_for_timeout(wait_ms)

    async def _human_browse_noise(self, linkedin_url: str, return_url: Optional[str] = None) -> None:
        """Best-effort human-like behavior: short waits, minor scrolls, and occasional tab detour."""
        try:
            # Variable dwell time and tiny movements.
            await self._human_pause(500, 1600)

            if random.random() < 0.9:
                await self.page.mouse.wheel(0, random.randint(250, 900))
                await self._human_pause(250, 700)

            if random.random() < 0.6:
                await self.page.mouse.move(random.randint(120, 900), random.randint(120, 650), steps=random.randint(8, 20))
                await self._human_pause(180, 500)

            # Occasionally visit another section briefly, then come back.
            if random.random() < 0.45:
                detour_section = random.choice(["people", "jobs", "about"]) 
                detour_url = self._to_company_section_url(linkedin_url, detour_section)
                if detour_url:
                    await self.page.goto(detour_url, wait_until="domcontentloaded", timeout=30000)
                    await self._human_pause(700, 1800)
                    await self.page.mouse.wheel(0, random.randint(180, 720))
                    await self._human_pause(250, 650)

            if return_url:
                await self.page.goto(return_url, wait_until="domcontentloaded", timeout=40000)
                await self._human_pause(350, 900)
        except Exception:
            return

    def _to_company_section_url(self, linkedin_url: str, section: str) -> str:
        base = (linkedin_url or "").strip()
        normalized = base.rstrip("/")

        m = re.search(r"(https?://www\.linkedin\.com/company/[^/]+)", normalized, flags=re.IGNORECASE)
        if not m:
            return ""

        root = m.group(1)
        sec = (section or "about").strip().lower()
        return f"{root}/{sec}/"

    async def _find_external_website(self) -> Optional[str]:
        try:
            links = await self.page.locator('a[href^="http"]').all()
            for a in links:
                href = await a.get_attribute("href")
                if not href:
                    continue
                if "linkedin.com" in href:
                    continue
                return href
        except Exception:
            return None
        return None

    async def _extract_followers_text(self) -> Optional[str]:
        # best-effort: search for visible text containing "followers"
        try:
            candidates = await self.page.locator('text=/followers/i').all()
            for c in candidates[:10]:
                t = (await c.inner_text()).strip()
                if "follower" in t.lower() and len(t) <= 50:
                    return t
        except Exception:
            pass
        return None