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

def fill_login(frame, login, password):
    inputs = frame.locator("input")
    count = inputs.count()
    log(f"Login frame inputs found: {count}")
    if count < 2:
        raise SystemExit("Not enough inputs in login frame.")
    inputs.nth(0).fill(login)
    inputs.nth(1).fill(password)

def click_login(frame):
    buttons = frame.get_by_role("button")
    if buttons.count() > 0:
        for i in range(buttons.count()):
            try:
                txt = (buttons.nth(i).inner_text() or "").strip().upper()
            except Exception:
                txt = ""
            if "ZALOGUJ" in txt:
                buttons.nth(i).click()
                return
        buttons.nth(0).click()
        return
    frame.get_by_text("Zaloguj się", exact=False).click()

def go_to_login(page):
    page.goto(LOGIN_URL, wait_until="networkidle")
    page.get_by_text("Zaloguj się", exact=False).click()
    page.wait_for_timeout(2000)

def login_user(page):
    frame = None
    for _ in range(20):
        frame = find_login_frame(page)
        if frame:
            break
        page.wait_for_timeout(500)
    if not frame:
        raise SystemExit("Login frame not found.")
    log(f"Found login frame: {frame.url}")
    fill_login(frame, LOGIN, PASSWORD)
    save_debug(page, "04_filled_login")
    click_login(frame)
    page.wait_for_timeout(3000)
    save_debug(page, "05_after_login")

def extract_week_dates(page):
    text = page.locator("body").inner_text(timeout=5000)
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    return dates

def target_week_visible(page, target):
    text = page.locator("body").inner_text(timeout=5000)
    return target.isoformat() in text

def try_click_booking(page, target_class):
    candidates = [
        f"tr:has-text('{target_class}')",
        f"div:has-text('{target_class}')",
        f"td:has-text('{target_class}')",
    ]
    for sel in candidates:
        try:
            row = page.locator(sel).first
            if row.count() == 0:
                continue
            text = row.inner_text(timeout=2000).upper()
            if target_class.upper() not in text:
                continue
            for btxt in ["ZAPISZ", "REZERW", "ZAPIS", "BOOK", "SIGN UP"]:
                btn = row.get_by_role("button", name=re.compile(btxt, re.I))
                if btn.count() > 0:
                    btn.first.click()
                    return True
                link = row.get_by_role("link", name=re.compile(btxt, re.I))
                if link.count() > 0:
                    link.first.click()
                    return True
            buttons = row.locator("button, a")
            for i in range(buttons.count()):
                try:
                    txt = (buttons.nth(i).inner_text() or "").strip().upper()
                except Exception:
                    txt = ""
                if any(x in txt for x in ["ZAPISZ", "REZERW", "ZAPIS", "BOOK", "SIGN UP"]):
                    buttons.nth(i).click()
                    return True
        except Exception:
            pass
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

        go_to_login(page)
        save_debug(page, "02_after_click")

        login_user(page)

        page.goto(f"{BASE_URL}/kalendarz-zajec", wait_until="networkidle")
        save_debug(page, "06_schedule")

        body = page.locator("body").inner_text(timeout=5000)
        log("Schedule page opened.")

        if norm(TARGET_CLASS) not in norm(body):
            log(f"Class text not found in current page text: {TARGET_CLASS}")
        else:
            log(f"Class text found on page: {TARGET_CLASS}")
            if try_click_booking(page, TARGET_CLASS):
                log("Clicked booking element.")
                page.wait_for_timeout(2000)
                save_debug(page, "07_after_booking_click")
            else:
                log("Could not find booking button in the row.")

        browser.close()

if __name__ == "__main__":
    main()
