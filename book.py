import os
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN = os.getenv("EFITNESS_LOGIN", "")
PASSWORD = os.getenv("EFITNESS_PASSWORD", "")
LOGIN_URL = "https://cf43300-cms.efitness.com.pl/login"

out = Path("output")
out.mkdir(exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(LOGIN_URL, wait_until="networkidle")

        out.joinpath("login_debug.html").write_text(page.content(), encoding="utf-8")
        out.joinpath("login_debug.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
        page.screenshot(path=str(out / "login_debug.png"), full_page=True)

        browser.close()

if __name__ == "__main__":
    main()
