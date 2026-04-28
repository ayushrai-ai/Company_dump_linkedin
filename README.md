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

---

## Scripts

### Scrape company + founder
```bash
python main.py
```
Paste a LinkedIn company URL. Scrapes the company page, auto-detects the founder (or asks for their URL), and scrapes their profile.

### Scrape a person directly
```bash
python scrape_person.py
```
Paste any LinkedIn profile URL. Scrapes that profile and saves it to `output/`.

### Dump raw DOM (debugging)
```bash
python dump_person_dom.py
```
Paste a profile URL → saves raw HTML files to `dom_dumps/<slug>/` for all subpages.

---

## Output

All results saved to `output/` as JSON.

| File | Contents |
|------|----------|
| `<CompanyName>.json` | Company data |
| `<CompanyName>__founder_<Name>.json` | Founder profile (via `main.py`) |
| `<Name>.json` | Person profile (via `scrape_person.py`) |

---

## What gets scraped

**Company:** `name, tagline, description, website, phone, headquarters, founded, industry, company_type, company_size, specialties, posts[]`

**Person:** `name, headline, followers, location, open_to_work, about, experiences[], educations[], accomplishments[], contacts[], posts[]`

---

## How it works

- `create_session.py` — logs in and saves cookies/storage to `linkedin_session.json`
- `main.py` — scrapes company then auto-detects and scrapes founder
- `scrape_person.py` — scrapes a single profile directly
- `dump_person_dom.py` — saves raw HTML of all profile subpages for debugging
- `company_scraper/company.py` — company page scraper
- `company_scraper/person.py` — profile scraper; navigates subpages: `/details/experience/`, `/details/education/`, `/details/honors/`, `/overlay/contact-info/`, `/recent-activity/all/`
- `company_scraper/browser.py` — Playwright browser lifecycle and session management
