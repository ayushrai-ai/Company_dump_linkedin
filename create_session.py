import asyncio
import logging

from company_scraper.browser import BrowserManager
from company_scraper.utils import is_logged_in

logging.basicConfig(level=logging.INFO)


async def main():
    session_file = "linkedin_session.json"

    async with BrowserManager(headless=False) as browser:
        page = browser.page

        # Go to login page
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        print("\n1) Login manually in the opened browser window.")
        print("2) Complete any email/phone verification, 2FA, CAPTCHA, etc.")
        print("3) When you're fully logged in and see the LinkedIn feed, come back here.\n")

        # Wait until logged in
        while True:
            if await is_logged_in(page):
                break
            await asyncio.sleep(1)

        print("[OK] Detected login. Saving session...")
        await browser.save_session(session_file)
        print(f"[OK] Saved session to: {session_file}")


        await page.wait_for_timeout(1000)


if __name__ == "__main__":
    asyncio.run(main())