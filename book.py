import os
import re
from datetime import date, timedelta, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://cf43300-cms.efitness.com.pl"
LOGIN_URL = f"{BASE_URL}/login"
SCHEDULE_URL = f"{BASE_URL}/kalendarz-zajec"

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
    LOG_PATH.write_text(LOG_PATH.read_text(encoding="utf-8") + line + "\n" if LOG_PATH.exists() else line + "\n", encoding="utf-8")

def norm(t):
    return re.sub(r"\s+", " ", (t or "")).strip().upper()

def main():
    target = date.today() + timedelta(days=DAYS_AHEAD)
    log(f"Target date: {target.isoformat()}")
    log(f"Target class: {TARGET_CLASS}")

    if not LOGIN or not PASSWORD:
        raise SystemExit("Missing EFITNESS_LOGIN or EFITNESS_PASSWORD secret.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(LOGIN_URL, wait_until="networkidle")

        inputs = page.locator("input")
        count = inputs.count()
        if count < 2:
            raise SystemExit(f"Cannot find login form inputs. Found inputs: {count}")

        inputs.nth(0).fill(LOGIN)
        inputs.nth(1).fill(PASSWORD)

        page.get_by_role("button", name=re.compile("zaloguj", re.I)).click()
        page.wait_for_load_state("networkidle")

        page.goto(SCHEDULE_URL, wait_until="networkidle")
        body = page.locator("body").inner_text(timeout=5000)
        log("Schedule page opened.")

        if norm(TARGET_CLASS) in norm(body):
            log(f"Found class text on page: {TARGET_CLASS}")
        else:
            log(f"Class text not found in current page text: {TARGET_CLASS}")

        Path(OUT / "page_text.txt").write_text(body, encoding="utf-8")
        browser.close()

if __name__ == "__main__":
    main()
