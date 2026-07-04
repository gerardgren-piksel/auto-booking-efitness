import re
from dataclasses import dataclass
from datetime import date, timedelta

from booking.days import DAY_MAP, PL_DAY_BY_WEEKDAY
from booking.utils import norm
from booking.config import BOOKING_RULES_RAW

@dataclass
class BookingRule:
    class_name: str
    day_name: str | None = None
    time_text: str | None = None

