import os
import re
from datetime import date, timedelta, datetime
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()

def save_debug(page, prefix):
    OUT.mkdir(exist_ok=True)
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
        raise RuntimeError("Not enough inputs in login frame.")
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
        raise RuntimeError("Login frame not found.")

    fill_login(frame, LOGIN, PASSWORD)
    click_login(frame)
    page.wait_for_timeout(3000)

def goto_schedule(page):
    page.goto(urljoin(BASE_URL, "kalendarz-zajec"), wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

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
        title = item["title"]
        if title == "Dalej" and f"day={target_s}" in href:
            return href

    for item in links:
        href = item["href"]
        if f"day={target_s}" in href:
            return href

    return None

def go_next_week(page):
    raw_before, _, end_before = current_range(page)
    log(f"Range before: {raw_before}")

    if not end_before:
        raise RuntimeError("Could not parse current week range.")

    target_day = end_before + timedelta(days=7)
    log(f"Expected next week link day=: {target_day.isoformat()}")

    href = get_next_week_href(page, target_day)
    log(f"Week next href found: {href}")

    if not href:
        raise RuntimeError("Week next href not found from day links.")

    absolute_url = urljoin(BASE_URL, href)
    log(f"Going directly to week URL: {absolute_url}")
    page.goto(absolute_url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    raw_after, _, _ = current_range(page)
    log(f"Range after goto: {raw_after}")

    return raw_before != raw_after

def overlay_visible(page):
    selectors = [
        "#OverlayEventContent",
        ".popupwindow",
        ".modal",
        ".ui-dialog",
        ".overlay",
    ]

    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() > 0 and loc.first.is_visible():
                return True
        except Exception:
            pass
    return False

def try_click_locator(page, loc):
    try:
        loc.scroll_into_view_if_needed()
    except Exception:
        pass

    try:
        loc.click(timeout=4000)
        page.wait_for_timeout(1500)
        if overlay_visible(page):
            return True
    except Exception:
        pass

    try:
        loc.click(timeout=4000, force=True)
        page.wait_for_timeout(1500)
        if overlay_visible(page):
            return True
    except Exception:
        pass

    try:
        box = loc.bounding_box()
        if box:
            page.mouse.click(
                box["x"] + box["width"] / 2,
                box["y"] + box["height"] / 2
            )
            page.wait_for_timeout(1500)
            if overlay_visible(page):
                return True
    except Exception:
        pass

    return False

def open_class_details(page, target_class):
    txt = page.get_by_text(target_class, exact=True)
    if txt.count() == 0:
        txt = page.get_by_text(target_class, exact=False)

    if txt.count() == 0:
        log(f"Text not found for class: {target_class}")
        return False

    base = txt.first
    candidates = [
        base,
        base.locator(".."),
        base.locator("..").locator(".."),
        base.locator("..").locator("..").locator(".."),
        page.locator(f".event:has-text('{target_class}')").first,
        page.locator(f".scheduleitem:has-text('{target_class}')").first,
        page.locator(f"td:has-text('{target_class}')").first,
    ]

    for idx, candidate in enumerate(candidates, start=1):
        try:
            if candidate.count() == 0:
                continue
        except Exception:
            continue

        try:
            text_preview = candidate.inner_text(timeout=1000)
        except Exception:
            text_preview = "<no text>"

        log(f"Trying candidate {idx}: {text_preview[:200]}")

        if try_click_locator(page, candidate.first if hasattr(candidate, 'first') else candidate):
            log(f"Overlay opened from candidate {idx}")
            return True

    return False

def click_booking(page):
    patterns = [
        r"ZAPISZ",
        r"ZAREZERWUJ",
        r"REZERWUJ",
        r"REZERWACJ",
        r"DOŁĄCZ",
        r"BOOK",
        r"SIGN UP",
    ]

    scopes = [
        page.locator("#OverlayEventContent"),
        page.locator(".popupwindow"),
        page.locator(".ui-dialog"),
        page.locator(".modal"),
        page.locator("body"),
    ]

    for scope in scopes:
        try:
            _ = scope.count()
        except Exception:
            continue

        for patt in patterns:
            try:
                btn = scope.get_by_role("button", name=re.compile(patt, re.I))
                if btn.count() > 0:
                    btn.first.click(timeout=4000, force=True)
                    return True
            except Exception:
                pass

            try:
                link = scope.get_by_role("link", name=re.compile(patt, re.I))
                if link.count() > 0:
                    link.first.click(timeout=4000, force=True)
                    return True
            except Exception:
                pass

            try:
                txt = scope.locator(f"text=/{patt}/i")
                if txt.count() > 0:
                    txt.first.click(timeout=4000, force=True)
                    return True
            except Exception:
                pass

    return False

def already_booked(page, target_class):
    try:
        body = norm(page.locator("body").inner_text(timeout=5000))
    except Exception:
        return False

    target_n = norm(target_class)
    if "ODWOŁAJ REZERWACJ" in body and target_n in body:
        return True
    return False

def main():
    target = date.today() + timedelta(days=DAYS_AHEAD)

    log(f"Working dir: {Path.cwd()}")
    log(f"Output dir: {OUT.resolve()}")
    log(f"Target date: {target.isoformat()}")
    log(f"Target class: {TARGET_CLASS}")

    if not LOGIN or not PASSWORD:
        raise RuntimeError("Missing EFITNESS_LOGIN or EFITNESS_PASSWORD secret.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2200})

        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.get_by_text("Zaloguj się", exact=False).click()
            page.wait_for_timeout(2000)

            login_user(page)
            save_debug(page, "05_after_login")

            goto_schedule(page)
            save_debug(page, "06_schedule_before_next")

            moved = go_next_week(page)
            log(f"Moved next week: {moved}")
            save_debug(page, "07_schedule_after_next")

            if already_booked(page, TARGET_CLASS):
                log(f"Already booked for class: {TARGET_CLASS}")
                save_debug(page, "08_already_booked")
                return

            body_after_week = norm(page.locator("body").inner_text(timeout=5000))
            if norm(TARGET_CLASS) not in body_after_week:
                log(f"Target class not found in week view: {TARGET_CLASS}")
                save_debug(page, "08_class_not_found")
                return

            opened = open_class_details(page, TARGET_CLASS)
            log(f"Opened class details: {opened}")
            save_debug(page, "09_after_class_open")

            booked = click_booking(page)
            log(f"Clicked booking control: {booked}")
            page.wait_for_timeout(3000)
            save_debug(page, "10_after_booking_click")

        except PlaywrightTimeoutError as e:
            log(f"Timeout: {e}")
            save_debug(page, "99_timeout")
            raise
        except Exception as e:
            log(f"Error: {e}")
            save_debug(page, "99_error")
            raise
        finally:
            browser.close()

if __name__ == "__main__":
    main()
