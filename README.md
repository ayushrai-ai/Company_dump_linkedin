# LinkedIn Scraper

Scrapes LinkedIn company pages and founder profiles using Playwright.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Step 1 — Save LinkedIn session (once)

```bash
python create_session.py
```

A browser opens → log in manually → session saved to `linkedin_session.json`.

## Step 2 — Run scraper

```bash
python main.py
```

Paste a LinkedIn company URL when prompted. The scraper will:
1. Scrape the company page
2. Auto-detect the founder (or ask you to paste their profile URL)
3. Scrape the founder's profile

## Step 3 — Dump raw DOM (debugging)

```bash
python dump_person_dom.py
```

Paste a profile URL → saves raw HTML files to `dom_dumps/<slug>/`.

---

## Output

All results saved to `output/` as JSON.

| File | Contents |
|------|----------|
| `<CompanyName>.json` | Company data |
| `<CompanyName>__founder_<Name>.json` | Founder profile |

---

## What gets scraped

**Company:** `name, tagline, description, website, phone, headquarters, founded, industry, company_type, company_size, specialties, posts[]`

**Person (founder):** `name, headline, followers, location, open_to_work, about, experiences[], educations[], accomplishments[], contacts[], posts[]`

---

## How it works

- `create_session.py` — logs in and saves cookies/storage to `linkedin_session.json`
- `main.py` — entry point; scrapes company then founder
- `company_scraper/company.py` — scrapes company pages
- `company_scraper/person.py` — scrapes profile pages (navigates to subpages: `/details/experience/`, `/details/education/`, `/details/honors/`, `/overlay/contact-info/`, `/recent-activity/all/`)
- `company_scraper/browser.py` — manages Playwright browser lifecycle and session
- `dump_person_dom.py` — saves raw HTML of all profile subpages for debugging
