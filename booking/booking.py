import re
from datetime import date
from urllib.parse import urljoin

from booking.config import BASE_URL
from booking.utils import log, norm

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