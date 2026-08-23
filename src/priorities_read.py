"""Read weekly priorities from a local file.

Deliberately NOT Google Docs. The Docs API has no per-document scope, so
reading one priorities doc would have required documents.readonly — read
access to every document in the account. A local file grants nothing.
"""
import re
from datetime import date

import config


def fetch_priorities() -> str:
    """Return the whole priorities file as text."""
    path = config.PRIORITIES_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Create it with a '## Week of M.D' heading — "
            f"see README.md for the format."
        )
    return path.read_text()


def week_label(day: date | None = None) -> str:
    """The '8.24' style label for the Monday of the given day's week."""
    day = day or date.today()
    monday = day - __import__("datetime").timedelta(days=day.weekday())
    return f"{monday.month}.{monday.day}"


def extract_week_section(text: str, label: str) -> str | None:
    """Return just the '## Week of <label>' section.

    Old weeks accumulate in the file; reading all of them would pull stale
    priorities into this week's plan.
    """
    pattern = rf"^##\s*Week of\s*{re.escape(label)}\s*$"
    lines = text.splitlines()

    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip(), re.IGNORECASE):
            start = i
            break
    if start is None:
        return None

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^##\s*Week of", lines[i].strip(), re.IGNORECASE):
            end = i
            break

    return "\n".join(lines[start:end]).strip()
