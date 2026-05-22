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

LOGIN_URL = "PUT_LOGIN_URL_HERE"
SCHEDULE_URL = "PUT_SCHEDULE_URL_HERE"
BOOK_URL = "PUT_BOOK_URL_HERE"

login_value = os.getenv("EFITNESS_LOGIN")
password_value = os.getenv("EFITNESS_PASSWORD")

if not login_value or not password_value:
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

def login():
    raise NotImplementedError("Tu wstawimy prawdziwy request logowania.")

def fetch_schedule(target_date):
    raise NotImplementedError("Tu wstawimy pobieranie grafiku.")

def book_class(class_id):
    raise NotImplementedError("Tu wstawimy request rezerwacji.")

if __name__ == "__main__":
    target_date = get_target_date(7)
    print("Cel:", target_date)
    print("Następny krok: login() -> fetch_schedule() -> book_class().")
