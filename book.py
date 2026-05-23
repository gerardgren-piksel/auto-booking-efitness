import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://cf43300-cms.efitness.com.pl"
LOGIN_URL = BASE_URL

LOGIN = os.getenv("EFITNESS_LOGIN", "")
PASSWORD = os.getenv("EFITNESS_PASSWORD", "")

out = Path("output")
out.mkdir(exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(LOGIN_URL, wait_until="networkidle")
        page.get_by_text("Zaloguj się", exact=False).click()

        out.joinpath("debug.html").write_text(page.content(), encoding="utf-8")
        out.joinpath("debug.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
        page.screenshot(path=str(out / "debug.png"), full_page=True)

        browser.close()

if __name__ == "__main__":
    main()
