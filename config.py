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
OWNER_NAME = os.getenv("OWNER_NAME", "Khushi")
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

# Where you travel from. Used to estimate commute around located events.
# Overridden by an origin named in an event's notes, or in the priorities file.
HOME_ADDRESS = os.getenv("HOME_ADDRESS", "40 N 4th St, Brooklyn, NY 11249")
OFFICE_ADDRESS = os.getenv("OFFICE_ADDRESS", "1230 Avenue of the Americas, New York, NY 10020")

# Event categories and their Google Calendar colours.
# Google exposes 11 fixed palette slots by ID; these are its own names for them.
CATEGORY_COLORS = {
    "focus":   "9",   # Blueberry  - deep work, studying, prep
    "social":  "4",   # Flamingo   - dinners, friends, events
    "workout": "10",  # Basil      - gym, sports, classes
    "errand":  "5",   # Banana     - admin, chores, appointments
    "travel":  "8",   # Graphite   - commute; deliberately muted, it is overhead
}
CATEGORIES = list(CATEGORY_COLORS)

TARGET_CALENDAR_ID = os.getenv("CALASSIST_CALENDAR_ID", "primary")

# Priorities live in a plain local file, NOT Google Docs. The Docs API has no
# per-document scope, so reading one doc would have meant granting read access
# to every document in the account. A local file grants nothing.
PRIORITIES_FILE = Path(
    os.getenv("PRIORITIES_FILE", Path.home() / "Documents" / "calassist-priorities.md")
)
