import os
import requests
from datetime import datetime, timedelta

TARGET_CLASSES = {
    0: ["FUNCTIONAL BODYBUILDING", "18:50"],
    1: ["CROSSFIT", "17:40"],
    2: ["CROSSFIT ATHLETE", "17:40"],
    3: ["GYMNASTICS", "17:40"],
    4: ["KETTLEBELLS", "17:40"],
    5: ["HYBRID RACE", "10:00"],
}

login = os.getenv("EFITNESS_LOGIN")
password = os.getenv("EFITNESS_PASSWORD")

if not login or not password:
    raise SystemExit("Brak sekretów EFITNESS_LOGIN lub EFITNESS_PASSWORD")

session = requests.Session()


def get_target_date(days_ahead=7):
    return (datetime.now() + timedelta(days=days_ahead)).date()


def should_book(class_name, class_time, target_dt):
    weekday = target_dt.weekday()
    expected = TARGET_CLASSES.get(weekday)
    if not expected:
        return False
    return expected[0] == class_name.upper() and expected[1] == class_time


if __name__ == "__main__":
    target_date = get_target_date(7)
    print("Sekrety są dostępne.")
    print("Cel:", target_date)
    print("Następny krok: logowanie i pobranie grafiku.")

