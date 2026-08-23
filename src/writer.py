"""Create calendar events.

THIS IS THE ONLY MODULE THAT WRITES TO YOUR CALENDAR. The agent cannot reach
it — main.py calls create_events only after you approve. If you ever find a
calendar write anywhere else in src/, that is a bug worth stopping for.
"""
from typing import NamedTuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from src.auth import get_credentials
from src.tools import Proposal


class WriteResult(NamedTuple):
    created: list[str]
    failed: list[tuple[str, str]]     # (title, error message)


def to_google_event(block: dict) -> dict:
    """Convert one proposal block into a Google Calendar event body."""
    tz_name = str(config.TIMEZONE)
    event = {
        "summary": block["title"],
        "description": f"Scheduled by CalAssist.\n\nWhy here: {block['reason']}",
        "start": {"dateTime": f"{block['day']}T{block['start']}:00", "timeZone": tz_name},
        "end": {"dateTime": f"{block['day']}T{block['end']}:00", "timeZone": tz_name},
    }
    # Unknown categories are rejected by validate_proposal long before this,
    # but a missing colour should never be the thing that blocks a write.
    color = config.CATEGORY_COLORS.get(block.get("category"))
    if color:
        event["colorId"] = color
    return event


def create_events(proposal: Proposal, calendar_id: str | None = None) -> WriteResult:
    """Create every block. Reports partial failure rather than hiding it."""
    calendar_id = calendar_id or config.TARGET_CALENDAR_ID
    service = build("calendar", "v3", credentials=get_credentials())

    created, failed = [], []
    for block in proposal.blocks:
        try:
            service.events().insert(
                calendarId=calendar_id, body=to_google_event(block)
            ).execute()
            created.append(block["title"])
        except HttpError as exc:
            failed.append((block["title"], str(exc)))

    return WriteResult(created=created, failed=failed)
