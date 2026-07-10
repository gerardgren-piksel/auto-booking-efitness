import os
import re
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urljoin
from booking.utils import log, norm, slug
from booking.rules import (
    BookingRule,
    normalize_day_name,
    normalize_class_text,
    parse_rules,
    date_matches_rule,
    weekday_number_from_rule,
    target_date_for_rule,
    next_matching_dates,
)
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from booking.config import (
    BASE_URL,
    LOGIN_URL,
    LOGIN,
    PASSWORD,
    BOOKING_RULES_RAW,
    DAYS_AHEAD,
    OUT,
)
from booking.days import DAY_MAP, PL_DAY_BY_WEEKDAY
from booking.debug import save_debug
from booking.login import login_user









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



def parse_hhmm_to_minutes(value: str | None):
    if not value:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", value)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))

def nearest_hour_label_minutes(page, event_locator):
    try:
        handle = event_locator.element_handle()
        if not handle:
            return None

        result = handle.evaluate("""
        (el) => {
            function textOf(node) {
                return (node && node.innerText ? node.innerText : '').replace(/\\s+/g, ' ').trim();
            }

            const eventRect = el.getBoundingClientRect();
            const all = Array.from(document.querySelectorAll('body *'));
            let best = null;

            for (const node of all) {
                const txt = textOf(node);
                if (!/^\\d{1,2}:\\d{2}$/.test(txt)) continue;

                const r = node.getBoundingClientRect();
                const dy = Math.abs((r.top + r.height / 2) - (eventRect.top + eventRect.height / 2));
                const dx = Math.abs((r.left + r.width / 2) - (eventRect.left + eventRect.width / 2));

                if (dx > 500) continue;

                const score = dy * 10 + dx;
                if (!best || score < best.score) {
                    best = { text: txt, score: score };
                }
            }

            return best ? best.text : null;
        }
        """)
        return parse_hhmm_to_minutes(result)
    except Exception:
        return None

def choose_candidates_by_time(page, decorated, target_time_text):
    target_minutes = parse_hhmm_to_minutes(target_time_text)
    if target_minutes is None or not decorated:
        return decorated

    scored = []

    for item in decorated:
        y, box, text = item
        label_minutes = nearest_hour_label_minutes(page, box)
        diff = abs(label_minutes - target_minutes) if label_minutes is not None else 999999
        scored.append((diff, 999999 if y is None else y, item, label_minutes, text))

    scored.sort(key=lambda x: (x[0], x[1]))

    for diff, y, _, label_minutes, text in scored:
        text_clean = re.sub(r"\s+", " ", text).strip()[:200]
        log(f"Time score diff={diff} y={y} label_minutes={label_minutes} text={text_clean}")

    best_item = scored[0][2]
    return [best_item]

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

        candidate_text = normalize_class_text(text)
        needle = normalize_class_text(rule.class_name)

        if needle in candidate_text:
            matched.append(box)
            continue

        if all(token in candidate_text for token in needle.split() if len(token) >= 4):
            matched.append(box)
            continue

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

    if rule.time_text:
        if normalize_class_text(rule.class_name) == "HYBRID RACE" and rule.time_text == "10:00":
            any_time = any(nearest_hour_label_minutes(page, box) is not None for _, box, _ in decorated)
            if any_time:
                by_time = choose_candidates_by_time(page, decorated, rule.time_text)
                if by_time:
                    return by_time

            if len(decorated) >= 2:
                return [decorated[-1]]
            if decorated:
                return [decorated[0]]

        by_time = choose_candidates_by_time(page, decorated, rule.time_text)
        if by_time:
            return by_time

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
    needle = normalize_class_text(rule.class_name)

    if needle in body:
        return True

    for token in needle.split():
        if len(token) >= 4 and token in body:
            return True

    return False

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
            today = datetime.now(
                ZoneInfo("Europe/Warsaw")
            ).date()

            warsaw_now = datetime.now(ZoneInfo("Europe/Warsaw"))

            log(
                f"Warsaw time: {warsaw_now.isoformat()} | "
                f"Today: {today.isoformat()} "
                f"({PL_DAY_BY_WEEKDAY[today.weekday()]})"
            )

            for rule in rules:
                target_date = target_date_for_rule(today, rule)
                log(
                    f"Rule target date: {rule.class_name} | "
                    f"{rule.day_name or '*'} | {rule.time_text or '*'} -> "
                    f"{target_date.isoformat()} ({PL_DAY_BY_WEEKDAY[target_date.weekday()]})"
                )

                result = try_book_rule_on_date(page, rule, target_date)
                if result:
                    log(f"SUCCESS for date {target_date.isoformat()} and rule: {rule}")
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