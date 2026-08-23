"""Configuration for CalAssist.

Work hours are blocked here BY RULE, not by reading events. CalAssist
connects to a personal Google account; work commitments live on a separate
calendar it cannot see. Without WEEKDAY_BLOCKED it would treat an empty
Tuesday 10am as free and propose deep work during office hours.
"""
import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Credentials live OUTSIDE the repo. This project is public; a secret that is
# not in the working tree cannot be committed by any accident.
CONFIG_DIR = Path(
    os.getenv("CALASSIST_CONFIG_DIR", Path.home() / ".config" / "calassist")
)
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
ENV_FILE = CONFIG_DIR / "env"

load_dotenv(ENV_FILE)

TIMEZONE = ZoneInfo("America/New_York")
MODEL = "claude-sonnet-5"

# Commute + office. Invisible to this app, so blocked by rule.
WEEKDAY_BLOCKED = (time(8, 30), time(17, 0))

# Preferred bookable windows.
WEEKDAY_BOOKABLE = [(time(17, 0), time(21, 0))]
WEEKEND_BOOKABLE = [(time(9, 0), time(21, 0))]

# Used ONLY when the week doesn't fit. Always produces a warning.
WEEKDAY_OVERFLOW = [(time(7, 0), time(8, 30))]
EVENING_OVERFLOW = [(time(21, 0), time(22, 0))]

# Minimum gap between a proposed block and any adjacent event.
BUFFER_MINUTES = 15

TARGET_CALENDAR_ID = os.getenv("CALASSIST_CALENDAR_ID", "primary")
PRIORITIES_DOC_ID = os.getenv("PRIORITIES_DOC_ID")
TASKS_DOC_ID = os.getenv("TASKS_DOC_ID")
