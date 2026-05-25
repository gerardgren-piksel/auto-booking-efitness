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

PL_DAY_BY_WEEKDAY = {
    0: "PONIEDZIAŁEK",
    1: "WTOREK",
    2: "ŚRODA",
    3: "CZWARTEK",
    4: "PIĄTEK",
    5: "SOBOTA",
    6: "NIEDZIELA",
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
    try:
        (OUT / f"{prefix}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        (OUT / f"{prefix}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(OUT / f"{prefix}.png"), full_page=True)
    except Exception:
        pass

def normalize_day_name(value: str | None):
    if not value:
        return None
    key = norm(value)
    return DAY_MAP.get(key, key)

def normalize_class_text(value: str) -> str:
    value = norm(value)
    value = re.sub(r"[.,:;!?]+$", "", value).strip()
    return value

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
            rules.append(
                BookingRule(
                    class_name=parts[0],
                    day_name=normalize_day_name(parts[1]),
                )
            )
        else:
            rules.append(
                BookingRule(
                    class_name=parts[0],
                    day_name=normalize_day_name(parts[1]),
                    time_text=parts[2],
                )
            )

    return rules

def date_matches_rule(target_date: date, rule: BookingRule):
    if not rule.day_name:
        return True
    return PL_DAY_BY_WEEKDAY[target_date.weekday()] == norm(rule.day_name)

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

def goto_day_schedule(page, target_date: date):
    url = urljoin(BASE_URL, f"kalendarz-zajec?day={target_date.isoformat()}&view=DayByHour")
    log(f"Opening day schedule: {url}")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

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
        page.wait_for_timeout(1200)
        if overlay_visible(page):
            return True
    except Exception:
        pass

    try:
        loc.click(timeout=4000, force=True)
        page.wait_for_timeout(1200)
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
            page.wait_for_timeout(1200)
            if overlay_visible(page):
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
    event_boxes = page.locator(".event")
    matched = []

    total = event_boxes.count()
    for i in range(total):
        box = event_boxes.nth(i)
        try:
            text = norm(box.inner_text(timeout=1000))
        except Exception:
            continue

        if normalize_class_text(rule.class_name) not in normalize_class_text(text):
            continue

        matched.append(box)

    decorated = []
    for box in matched:
        try:
            text = box.inner_text(timeout=1000)
        except Exception:
            text = "<no text>"

        try:
            bb = box.bounding_box()
            y = round(bb["y"], 1) if bb else None
        except Exception:
            y = None

        decorated.append((y, box, text))

    decorated.sort(key=lambda x: (999999 if x[0] is None else x[0]))

    log(f"Matched event boxes for {rule.class_name}: {len(decorated)}")
    for idx, (y, _, text) in enumerate(decorated, start=1):
        preview = re.sub(r"\s+", " ", text).strip()[:250]
        log(f"Candidate {idx} y={y} text={preview}")

    cls = normalize_class_text(rule.class_name)

    if rule.time_text:
        if cls == "HYBRID RACE" and rule.time_text == "10:00":
            available = []
            for item in decorated:
                _, _, text = item
                nt = norm(text)
                if "-1 WOLNYCH" in nt or "-2 WOLNYCH" in nt or "-3 WOLNYCH" in nt or "-4 WOLNYCH" in nt:
                    continue
                available.append(item)

            if available:
                return [available[-1]]

            if len(decorated) >= 2:
                return [decorated[-1]]

        if cls == "FUNCTIONAL BODYBUILDING" and rule.time_text == "18:50":
            available = []
            for item in decorated:
                _, _, text = item
                nt = norm(text)
                if "-1 WOLNYCH" in nt or "-2 WOLNYCH" in nt or "-3 WOLNYCH" in nt or "-4 WOLNYCH" in nt:
                    continue
                available.append(item)

            if available:
                return [available[-1]]

            if decorated:
                return [decorated[-1]]

        if cls == "CROSSFIT" and rule.time_text == "17:40":
            filtered = []
            for item in decorated:
                _, _, text = item
                nt = norm(text)
                if "-4 WOLNYCH" in nt or "-3 WOLNYCH" in nt or "-2 WOLNYCH" in nt or "-1 WOLNYCH" in nt:
                    continue
                if "FUNDAMENTALS" in nt:
                    continue
                filtered.append(item)

            if filtered:
                return [filtered[0]]

    return decorated




def overlay_matches_rule(ov_text: str, rule: BookingRule):
    if normalize_class_text(rule.class_name) not in normalize_class_text(ov_text):
        return False

    if rule.time_text:
        if norm(rule.time_text) in ov_text:
            return True

        if rule.class_name.strip().upper().startswith("HYBRID RACE"):
            if "BRAK WOLNYCH MIEJSC" in ov_text or "LISTĘ REZERWOWĄ" in ov_text:
                return False
            if "ZAPISZ SIĘ" in ov_text:
                return True

        if rule.class_name.strip().upper().startswith("FUNCTIONAL BODYBUILDING"):
            if "ZAPISZ SIĘ" in ov_text or "JESTEŚ JUŻ ZAPISANY" in ov_text:
                return True

        if rule.class_name.strip().upper().startswith("CROSSFIT"):
            if "ZAPISZ SIĘ" in ov_text or "JESTEŚ JUŻ ZAPISANY" in ov_text:
                return True

        return False

    return True

def open_class_details_matching_rule(page, rule: BookingRule):
    candidates = event_candidates_for_rule(page, rule)

    for idx, (_, candidate, preview_text) in enumerate(candidates, start=1):
        preview_clean = re.sub(r"\s+", " ", preview_text).strip()[:200]
        log(f"Trying candidate {idx}: {preview_clean}")

        close_overlay_if_possible(page)
        page.wait_for_timeout(500)

        if not try_click_locator(page, candidate):
            continue

        ov_text = overlay_text(page)
        log(f"Overlay text after candidate {idx}: {ov_text[:500]}")

        if overlay_matches_rule(ov_text, rule):
            log(f"Overlay accepted from candidate {idx}")
            return True

        log(f"Candidate {idx} rejected.")
        close_overlay_if_possible(page)
        page.wait_for_timeout(500)

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
    if "BRAK WOLNYCH MIEJSC" in text and "LISTĘ REZERWOWĄ" in text:
        return False

    success_markers = [
        "ODWOŁAJ REZERWACJ",
        "JESTEŚ JUŻ ZAPISANY",
        "ZOSTAŁEŚ ZAPISANY",
        "REZERWACJA ZOSTAŁA",
    ]
    return any(marker in text for marker in success_markers)

def page_contains_rule(page, rule: BookingRule):
    body = norm(page.locator("body").inner_text(timeout=5000))
    if normalize_class_text(rule.class_name) not in normalize_class_text(body):
        return False
    return True

def try_book_rule_on_date(page, rule: BookingRule, target_date: date):
    close_overlay_if_possible(page)
    page.wait_for_timeout(700)

    rule_label = f"{target_date.isoformat()} | {rule.class_name} | {rule.day_name or '*'} | {rule.time_text or '*'}"
    log(f"Checking rule: {rule_label}")

    goto_day_schedule(page, target_date)
    save_debug(page, f"day_{target_date.isoformat()}_{slug(rule.class_name)}_before")

    if not page_contains_rule(page, rule):
        log(f"Rule not present in day view: {rule_label}")
        return False

    opened = open_class_details_matching_rule(page, rule)
    log(f"Opened class details for rule {rule_label}: {opened}")
    save_debug(page, f"day_{target_date.isoformat()}_{slug(rule.class_name)}_open")

    if not opened:
        return False

    ov_text = overlay_text(page)
    log(f"Overlay text preview: {ov_text[:500]}")

    if "JESTEŚ JUŻ ZAPISANY" in ov_text or "ODWOŁAJ REZERWACJ" in ov_text:
        log(f"Already booked in overlay for rule: {rule_label}")
        close_overlay_if_possible(page)
        return False

    if "BRAK WOLNYCH MIEJSC" in ov_text and "LISTĘ REZERWOWĄ" in ov_text:
        log(f"No free spots for rule: {rule_label}")
        close_overlay_if_possible(page)
        return False

    booked = click_booking(page)
    log(f"Clicked booking control for rule {rule_label}: {booked}")
    page.wait_for_timeout(3000)
    save_debug(page, f"day_{target_date.isoformat()}_{slug(rule.class_name)}_after_click")

    confirmed = booking_success_text_present(page)
    log(f"Booking confirmed for rule {rule_label}: {confirmed}")
    save_debug(page, f"day_{target_date.isoformat()}_{slug(rule.class_name)}_after_check")

    close_overlay_if_possible(page)
    return confirmed

def main():
    rules = parse_rules()

    log(f"Working dir: {Path.cwd()}")
    log(f"Output dir: {OUT.resolve()}")
    log(f"DAYS_AHEAD: {DAYS_AHEAD}")
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

            booked_any = False

            start_date = date.today()
            end_date = date.today() + timedelta(days=DAYS_AHEAD)

            log(f"Date window: {start_date.isoformat()} -> {end_date.isoformat()}")

            current = start_date
            while current <= end_date:
                log(f"Processing date: {current.isoformat()} ({PL_DAY_BY_WEEKDAY[current.weekday()]})")

                for rule in rules:
                    if not date_matches_rule(current, rule):
                        continue

                    result = try_book_rule_on_date(page, rule, current)
                    if result:
                        log(f"SUCCESS for date {current.isoformat()} and rule: {rule}")
                        booked_any = True

                current += timedelta(days=1)

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
