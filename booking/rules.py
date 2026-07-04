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

    def weekday_number_from_rule(rule: BookingRule):
    if not rule.day_name:
        return None
        
    def target_date_for_rule(today: date, rule: BookingRule):
    weekday_num = weekday_number_from_rule(rule)

    if weekday_num is None:
        return today + timedelta(days=7)

    days_until = (weekday_num - today.weekday()) % 7
    if days_until == 0:
        days_until = 7

    return today + timedelta(days=days_until)

    def next_matching_dates(start: date, rule: BookingRule, days_ahead: int):
    end = start + timedelta(days=days_ahead)
    current = start
    while current <= end:
        if date_matches_rule(current, rule):
            yield current
        current += timedelta(days=1)


