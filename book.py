import os
import re
from datetime import date, timedelta, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://cf43300-cms.efitness.com.pl"
LOGIN_URL = BASE_URL

LOGIN = os.getenv("EFITNESS_LOGIN", "")
PASSWORD = os.getenv("EFITNESS_PASSWORD", "")
TARGET_CLASS = os.getenv("TARGET_CLASS", "KETTLEBELLS")
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "7"))

OUT = Path("output")
OUT.mkdir(exist_ok=True)
LOG_PATH = OUT / "run.log"

def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} | {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().upper()

def save_debug(page, prefix):
    (OUT / f"{prefix}.html").write_text(page.content(), encoding="utf-8")
    (OUT / f"{prefix}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    page.screenshot(path=str(OUT / f"{prefix}.png"), full_page=True)

def find_login_frame(page):
    for frame in page.frames:
        if "Login/SystemLogin" in frame.url:
            return frame
    return None

def main():
    target = date.today() + timedelta(days=DAYS_AHEAD)
    log(f"Target date: {target.isoformat()}")
    log(f"Target class: {TARGET_CLASS}")

    if not LOGIN or not PASSWORD:
        raise SystemExit("Missing EFITNESS_LOGIN or EFITNESS_PASSWORD secret.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})

        page.goto(LOGIN_URL, wait_until="networkidle")
        save_debug(page, "01_home")

        page.get_by_text("Zaloguj się", exact=False).click()
        page.wait_for_timeout(2000)
        save_debug(page, "02_after_click")

        frame = None
        for _ in range(20):
            frame = find_login_frame(page)
            if frame:
                break
            page.wait_for_timeout(500)

        if not frame:
            raise SystemExit("Login frame not found.")

        log(f"Found login frame: {frame.url}")
        save_debug(page, "03_before_fill")

        frame.get_by_label("Login").fill(LOGIN)
        frame.get_by_label("Hasło").fill(PASSWORD)
        save_debug(page, "04_filled_login")

        frame.get_by_role("button", name=re.compile("zaloguj", re.I)).click()
        page.wait_for_timeout(3000)
        save_debug(page, "05_after_login")

        page.goto(f"{BASE_URL}/kalendarz-zajec", wait_until="networkidle")
        save_debug(page, "06_schedule")

        body = page.locator("body").inner_text(timeout=5000)
        log("Schedule page opened.")

        if norm(TARGET_CLASS) in norm(body):
            log(f"Found class text on page: {TARGET_CLASS}")
        else:
            log(f"Class text not found in current page text: {TARGET_CLASS}")

        browser.close()

if __name__ == "__main__":
    main()
