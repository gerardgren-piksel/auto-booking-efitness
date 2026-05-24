import os
import re
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://cf43300-cms.efitness.com.pl/"
LOGIN_URL = BASE_URL

LOGIN = os.getenv("EFITNESS_LOGIN", "")
PASSWORD = os.getenv("EFITNESS_PASSWORD", "")
BOOKING_RULES_RAW = os.getenv("BOOKING_RULES", "")
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "7"))

OUT = Path("output")
OUT.mkdir(exist_ok=True)
LOG_PATH = OUT / "run.log"

DAY_MAP = {
    "MONDAY": "PONIEDZIAŁEK",
    "TUESDAY": "WTOREK",
    "WEDNESDAY": "ŚRODA",
    "THURSDAY": "CZWARTEK",
    "FRIDAY": "PIĄTEK",
    "SATURDAY": "SOBOTA",
    "SUNDAY": "NIEDZIELA",
    "PONIEDZIAŁEK": "PONIEDZIAŁEK",
    "WTOREK": "WTOREK",
    "ŚRODA": "ŚRODA",
    "SRODA": "ŚRODA",
    "CZWARTEK": "CZWARTEK",
    "PIĄTEK": "PIĄTEK",
    "PIATEK": "PIĄTEK",
    "SOBOTA": "SOBOTA",
    "NIEDZIELA": "NIEDZIELA",
}

@dataclass
class BookingRule:
    class_name: str
    day_name: str | None = None
    time_text: str | None = None

def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} | {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()

def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:80]

def save_debug(page, prefix):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{prefix}.html").write_text(page.content(), encoding="utf-8")
    (OUT / f"{prefix}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    page.screenshot(path=str(OUT / f"{prefix}.png"), full_page=True)

def normalize_day_name(value: str | None):
    if not value:
        return None
    key = norm(value)
    return DAY_MAP.get(key, key)

def parse_rules():
    rules = []
    raw = BOOKING_RULES_RAW.strip()

    if not raw:
        return [BookingRule(class_name="KETTLEBELLS")]

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p]

        if len(parts) == 1:
            rules.append(BookingRule(class_name=parts[0]))
        elif len(parts) == 2:
            rules.append(BookingRule(
                class_name=parts[0],
                day_name=normalize_day_name(parts[1]),
            ))
        else:
            rules.append(BookingRule(
                class_name=parts[0],
                day_name=normalize_day_name(parts[1]),
                time_text=parts[2],
            ))

    return rules

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

def registered_section_text(page):
    candidates = [
        page.locator("#calendarregisteredmeetings"),
        page.locator(".calendarregisteredmeetings"),
    ]

    for loc in candidates:
        try:
            if loc.count() == 0:
                continue
            return norm(loc.first.inner_text(timeout=5000))
        except Exception:
            pass

    return ""

def normalize_class_text(value: str) -> str:
    value = norm(value)
    value = re.sub(r"[.,:;!?]+$", "", value).strip()
    return value

def already_booked(page, rule: BookingRule):
    text = registered_section_text(page)
    log(f"Registered meetings section: {text[:500]}")

    if normalize_class_text(rule.class_name) not in normalize_class_text(text):
        return False
    if rule.day_name and norm(rule.day_name) not in text:
        return False
    if rule.time_text and norm(rule.time_text) not in text:
        return False
    return True

def close_overlay_if_possible(page):
    candidates = [
        page.get_by_role("button", name=re.compile(r"zamknij|close", re.I)),
        page.locator(".ui-dialog-titlebar-close"),
        page.locator(".popupwindow .close"),
        page.locator(".modal .close"),
    ]

    for loc in candidates:
        try:
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=2000, force=True)
                page.wait_for_timeout(1000)
                return
        except Exception:
            pass

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
    except Exception:
        pass

def event_candidates_for_rule(page, rule: BookingRule):
    text_locator = page.get_by_text(rule.class_name, exact=True)
    if text_locator.count() == 0:
        text_locator = page.get_by_text(rule.class_name, exact=False)

    candidates = []

    for i in range(min(text_locator.count(), 10)):
        base = text_locator.nth(i)
        candidates.extend([
            base,
            base.locator(".."),
            base.locator("..").locator(".."),
            base.locator("..").locator("..").locator(".."),
        ])

    candidates.extend([
        page.locator(f".event:has-text('{rule.class_name}')"),
        page.locator(f".scheduleitem:has-text('{rule.class_name}')"),
        page.locator(f"td:has-text('{rule.class_name}')"),
        page.locator(f"div:has-text('{rule.class_name}')"),
        page.locator(f"a:has-text('{rule.class_name}')"),
    ])

    flat = []
    for c in candidates:
        try:
            cnt = c.count()
            for i in range(min(cnt, 5)):
                flat.append(c.nth(i))
        except Exception:
            pass

    return flat

def candidate_matches_rule(candidate, rule: BookingRule):
    try:
        text = norm(candidate.inner_text(timeout=1000))
    except Exception:
        return False

    if normalize_class_text(rule.class_name) not in normalize_class_text(text):
        return False
    if rule.day_name and norm(rule.day_name) not in text:
        return False
    if rule.time_text and norm(rule.time_text) not in text:
        return False
    return True

def open_class_details(page, rule: BookingRule):
    candidates = event_candidates_for_rule(page, rule)

    for idx, candidate in enumerate(candidates, start=1):
        try:
            text_preview = candidate.inner_text(timeout=1000)
        except Exception:
            text_preview = "<no text>"

        if not candidate_matches_rule(candidate, rule):
            continue

        log(f"Trying candidate {idx}: {text_preview[:200]}")

        if try_click_locator(page, candidate):
            log(f"Overlay opened from candidate {idx}")
            return True

    if not rule.day_name and not rule.time_text:
        fallback = page.get_by_text(rule.class_name, exact=False)
        for i in range(min(fallback.count(), 5)):
            cand = fallback.nth(i)
            try:
                log(f"Trying fallback candidate {i + 1}")
                if try_click_locator(page, cand):
                    return True
            except Exception:
                pass

    return False

def overlay_text(page):
    selectors = [
        "#OverlayEventContent",
        ".popupwindow",
        ".ui-dialog",
        ".modal",
    ]
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() > 0 and loc.first.is_visible():
                return norm(loc.first.inner_text(timeout=3000))
        except Exception:
            pass
    return ""

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

def booking_success_text_present(page):
    text = overlay_text(page) + " " + norm(page.locator("body").inner_text(timeout=5000))
    success_markers = [
        "ODWOŁAJ REZERWACJ",
        "JESTEŚ ZAPISANY",
        "ZOSTAŁEŚ ZAPISANY",
        "REZERWACJA ZOSTAŁA",
        "ANULUJ REZERWACJ",
    ]
    return any(marker in text for marker in success_markers)

def rule_present_in_week_view(page, rule: BookingRule):
    body = norm(page.locator("body").inner_text(timeout=5000))
    if normalize_class_text(rule.class_name) not in normalize_class_text(body):
        return False
    if rule.day_name and norm(rule.day_name) not in body:
        return False
    if rule.time_text and norm(rule.time_text) not in body:
        return False
    return True

def try_book_rule(page, rule: BookingRule):
    rule_label = f"{rule.class_name} | {rule.day_name or '*'} | {rule.time_text or '*'}"
    log(f"Checking rule: {rule_label}")

    if already_booked(page, rule):
        log(f"Already booked for rule: {rule_label}")
        return False

    if not rule_present_in_week_view(page, rule):
        log(f"Rule not present in week view: {rule_label}")
        return False

    opened = open_class_details(page, rule)
    log(f"Opened class details for rule {rule_label}: {opened}")
    save_debug(page, f"09_after_class_open_{slug(rule_label)}")

    if not opened:
        return False

    ov_text = overlay_text(page)
    log(f"Overlay text preview: {ov_text[:500]}")

    if rule.day_name and norm(rule.day_name) not in ov_text:
        log(f"Overlay day mismatch for rule: {rule_label}")
        close_overlay_if_possible(page)
        return False

    if rule.time_text and norm(rule.time_text) not in ov_text:
        log(f"Overlay time mismatch for rule: {rule_label}")
        close_overlay_if_possible(page)
        return False

    booked = click_booking(page)
    log(f"Clicked booking control for rule {rule_label}: {booked}")
    page.wait_for_timeout(3000)
    save_debug(page, f"10_after_booking_click_{slug(rule_label)}")

    confirmed = already_booked(page, rule) or booking_success_text_present(page)
    log(f"Booking confirmed for rule {rule_label}: {confirmed}")
    save_debug(page, f"11_after_booking_check_{slug(rule_label)}")

    close_overlay_if_possible(page)
    return confirmed or booked

def main():
    target = date.today() + timedelta(days=DAYS_AHEAD)
    rules = parse_rules()

    log(f"Working dir: {Path.cwd()}")
    log(f"Output dir: {OUT.resolve()}")
    log(f"Target date: {target.isoformat()}")
    log(f"Booking rules: {rules}")

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

            booked_any = False

            for rule in rules:
                result = try_book_rule(page, rule)
                if result:
                    log(f"SUCCESS for rule: {rule}")
                    booked_any = True

            if not booked_any:
                log("No rule was booked.")
                save_debug(page, "12_no_rule_booked")

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
