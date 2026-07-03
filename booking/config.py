import os
from pathlib import Path

BASE_URL = "https://cf43300-cms.efitness.com.pl/"
LOGIN_URL = BASE_URL

LOGIN = os.getenv("EFITNESS_LOGIN", "")
PASSWORD = os.getenv("EFITNESS_PASSWORD", "")
BOOKING_RULES_RAW = os.getenv("BOOKING_RULES", "")
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "7"))

OUT = Path("output")
OUT.mkdir(exist_ok=True)