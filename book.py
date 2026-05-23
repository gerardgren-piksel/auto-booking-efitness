import os
import re
from datetime import date, timedelta, datetime
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://cf43300-cms.efitness.com.pl/"
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
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().upper()

def save_debug(page, prefix):
    (OUT / f"{prefix}.html").write_text(page.content(), encoding="utf-8")
    (OUT / f"{prefix}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    page.screenshot(path=str(OUT / f"{prefix}.png"), full_page=True)

def current_range(page):
    txt = page.locator("body").inner_text(timeout=5000)
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+do\s+(\d{4}-\d{2}-\d{2})", txt)
    if not m:
        return None, None, None
    raw = m.group(0)
    start = date.fromisoformat(m.group(1))
    end = date.fromisoformat(m.group(2))
    return raw, start, end

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
    for i in range(buttons.count()):
        try:
            txt = (buttons.nth(i).inner_text() or "").strip().upper()
        except Exception:
            txt = ""
        if "ZALOGUJ" in txt:
            buttons.nth(i).click()
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
    fill_login(frame, LOGIN, PASSWORD)
    save_debug(page, "04_filled_login")
    click_login(frame)
    page.wait_for_timeout(3000)
    save_debug(page, "05_after_login")

def goto_schedule(page):
    page.goto(urljoin(BASE_URL, "kalendarz-zajec"), wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    save_debug(page, "06_schedule_before_next")

def extract_all_day_links(page):
    links = page.locator("a[href*='day=']")
    data = []
    count = links.count()
    for i in range(count):
        a = links.nth(i)
        try:
            href = a.get_attribute("href") or ""
            title = a.get_attribute("title") or ""
            text = (a.inner_text() or "").strip()
        except Exception:
            continue
        data.append({"href": href, "title": title, "text": text})
    return data

def get_next_week_href(page, target_day):
    links = extract_all_day_links(page)
    log(f"All day links: {links}")

    target_s = target_day.isoformat()
    for item in links:
        href = item["href"]
        if f"day={target_s}" in href:
            return href

    return None

def go_next_week(page):
    raw_before, start_before, end_before = current_range(page)
    log(f"Range before: {raw_before}")

    if not end_before:
        save_debug(page, "07_no_range_found")
        raise SystemExit("Could not parse current week range")

    target_day = end_before + timedelta(days=6)
    log(f"Expected next week link day=: {target_day.isoformat()}")

    href = get_next_week_href(page, target_day)
    log(f"Week next href found: {href}")

    if not href:
        save_debug(page, "07_next_link_not_found")
        raise SystemExit("Week next href not found from day links")

    absolute_url = urljoin(BASE_URL, href)
    log(f"Going directly to week URL: {absolute_url}")
    page.goto(absolute_url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    raw_after, _, _ = current_range(page)
    log(f"Range after goto: {raw_after}")

    return raw_before != raw_after

def open_class_details(page, target_class):
    cards = page.locator(".event")
    count = cards.count()

    for i in range(count):
        card = cards.nth(i)
        try:
            name = card.locator(".eventname").inner_text(timeout=2000).strip()
        except Exception:
            continue

        if norm(name) != norm(target_class):
            continue

        try:
            card.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            card.click(force=True)
            return True
        except Exception:
            pass

    return False

def click_booking_in_overlay(page):
    patterns = [r"ZAPISZ", r"REZERW", r"DOŁĄCZ", r"BOOK", r"SIGN UP"]
    scopes = [page.locator("#OverlayEventContent"), page.locator(".popupwindow"), page.locator("body")]

    for scope in scopes:
        for patt in patterns:
            try:
                btn = scope.get_by_role("button", name=re.compile(patt, re.I))
                if btn.count() > 0:
                    btn.first.click(force=True)
                    return True
                link = scope.get_by_role("link", name=re.compile(patt, re.I))
                if link.count() > 0:
                    link.first.click(force=True)
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
        page = browser.new_page(viewport={"width": 1440, "height": 2200})

        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.get_by_text("Zaloguj się", exact=False).click()
        page.wait_for_timeout(2000)
        login_user(page)

        goto_schedule(page)

        moved = go_next_week(page)
        log(f"Moved next week: {moved}")
        save_debug(page, "07_schedule_after_next")

        body = page.locator("body").inner_text(timeout=5000)
        if norm(TARGET_CLASS) in norm(body):
            log(f"Found class text after moving week: {TARGET_CLASS}")
            opened = open_class_details(page, TARGET_CLASS)
            log(f"Opened class details: {opened}")
            page.wait_for_timeout(2500)
            save_debug(page, "08_after_class_open")

            booked = click_booking_in_overlay(page)
            log(f"Clicked booking control: {booked}")
            page.wait_for_timeout(2500)
            save_debug(page, "09_after_booking_click")
        else:
            log(f"Target class not found after moving week: {TARGET_CLASS}")
            save_debug(page, "08_class_not_found")

        browser.close()

if __name__ == "__main__":
    main()
