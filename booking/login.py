from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from booking.config import (
    BASE_URL,
    LOGIN_URL,
    LOGIN,
    PASSWORD,
)

from booking.utils import log
from booking.debug import save_debug

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
