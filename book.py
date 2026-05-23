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
    if inputs.count() < 2:
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

def goto_schedule(page):
    page.goto(f"{BASE_URL}/kalendarz-zajec", wait_until="networkidle")
    save_debug(page, "06_schedule_before_next")

def next_visible_button(page):
    locators = [
        page.locator("button:visible"),
        page.locator("a:visible"),
        page.locator("div:visible"),
        page.locator("span:visible"),
    ]
    for loc in locators:
        try:
            c = loc.count()
            for i in range(min(c, 80)):
                try:
                    txt = (loc.nth(i).inner_text() or "").strip()
                except Exception:
                    txt = ""
                if any(k in norm(txt) for k in ["→", "›", "NASTĘP", "NEXT"]):
                    return loc.nth(i)
        except Exception:
            pass
    return None

def go_next_week(page):
    before = page.locator("body").inner_text(timeout=5000)
    target_range = None
    m = re.search(r"\d{4}-\d{2}-\d{2}\s+do\s+\d{4}-\d{2}-\d{2}", before)
    if m:
        target_range = m.group(0)

    for _ in range(8):
        btn = next_visible_button(page)
        if not btn:
            log("Next week button not found.")
            return False
        try:
            btn.click()
        except Exception:
            try:
                btn.click(force=True)
            except Exception:
                return False
        page.wait_for_timeout(1800)
        after = page.locator("body").inner_text(timeout=5000)
        if target_range and target_range not in after:
            return True
        if not target_range and before != after:
            return True
    return False

def click_booking_for_class(page, target_class):
    candidates = [
        page.locator(f"tr:has-text('{target_class}')"),
        page.locator(f"div:has-text('{target_class}')"),
        page.locator(f"td:has-text('{target_class}')"),
    ]
    for container in candidates:
        try:
            if container.count() == 0:
                continue
            row = container.first
            txt = row.inner_text(timeout=3000)
            if target_class.upper() not in norm(txt):
                continue
            for patt in ["ZAPISZ", "REZERW", "ZAPIS", "BOOK", "SIGN UP"]:
                btn = row.get_by_role("button", name=re.compile(patt, re.I))
                if btn.count() > 0:
                    btn.first.click()
                    return True
                link = row.get_by_role("link", name=re.compile(patt, re.I))
                if link.count() > 0:
                    link.first.click()
                    return True
            controls = row.locator("button, a")
            for i in range(controls.count()):
                try:
                    t = (controls.nth(i).inner_text() or "").strip().upper()
                except Exception:
                    t = ""
                if any(x in t for x in ["ZAPISZ", "REZERW", "ZAPIS", "BOOK", "SIGN UP"]):
                    controls.nth(i).click()
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
        page.get_by_text("Zaloguj się", exact=False).click()
        page.wait_for_timeout(2000)
        login_user(page)

        goto_schedule(page)
        if go_next_week(page):
            log("Moved to next week.")
        else:
            log("Could not confirm next week navigation.")
        save_debug(page, "07_schedule_next_week")

        body = page.locator("body").inner_text(timeout=5000)
        if norm(TARGET_CLASS) in norm(body):
            log(f"Class text found on next week page: {TARGET_CLASS}")
            if click_booking_for_class(page, TARGET_CLASS):
                log("Clicked booking element.")
                page.wait_for_timeout(3000)
                save_debug(page, "08_after_booking_click")
            else:
                log("Could not find booking button in the row.")
                save_debug(page, "08_no_booking_button")
        else:
            log(f"Class text not found on next week page: {TARGET_CLASS}")
            save_debug(page, "08_class_not_found")

        browser.close()

if __name__ == "__main__":
    main()
