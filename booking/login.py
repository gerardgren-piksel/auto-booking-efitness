from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from booking.config import (
    BASE_URL,
    LOGIN_URL,
    LOGIN,
    PASSWORD,
)

from booking.utils import log
from booking.debug import save_debug