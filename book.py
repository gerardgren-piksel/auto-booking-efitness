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

def fill_login_in_context(ctx):
    try:
        ctx.get_by_label("Login").fill(LOGIN)
        ctx.get_by_label("Hasło").fill(PASSWORD)
        ctx.get_by_role("button", name=re.compile("zaloguj", re.I)).click()
        return True
    except Exception:
        return False

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
        page.wait_for_timeout(1500)
        save_debug(page, "02_after_click")

        if fill_login_in_context(page):
            log("Filled login in main page")
        else:
            for i, frame in enumerate(page.frames):
                try:
                    if frame.get_by_label("Login").count() > 0 or frame.get_by_text("Login").count() > 0:
                        log(f"Trying frame {i}: {frame.url}")
                        if fill_login_in_context(frame):
                            log(f"Filled login in frame {i}")
                            break
                except Exception:
                    pass

        page.wait_for_timeout(2000)
        save_debug(page, "03_after_login")

        page.goto(f"{BASE_URL}/kalendarz-zajec", wait_until="networkidle")
        save_debug(page, "04_schedule")

        body = page.locator("body").inner_text(timeout=5000)
        log("Schedule page opened.")

        if norm(TARGET_CLASS) in norm(body):
            log(f"Found class text on page: {TARGET_CLASS}")
        else:
            log(f"Class text not found in current page text: {TARGET_CLASS}")

        browser.close()

if __name__ == "__main__":
    main()
