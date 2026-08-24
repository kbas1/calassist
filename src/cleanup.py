"""Remove blocks CalAssist created. Never touches anything you made yourself."""
from datetime import datetime, timedelta

from googleapiclient.discovery import build

import config
from src.auth import get_credentials
from src.calendar_read import Event


def find_written_blocks(start: datetime, end: datetime) -> list[dict]:
    """Raw calendar entries CalAssist wrote, within a window."""
    service = build("calendar", "v3", credentials=get_credentials())
    items = (
        service.events()
        .list(calendarId=config.TARGET_CALENDAR_ID, timeMin=start.isoformat(),
              timeMax=end.isoformat(), singleEvents=True, orderBy="startTime")
        .execute()
        .get("items", [])
    )
    return [e for e in items
            if "Scheduled by CalAssist" in (e.get("description") or "")]


def delete_blocks(events: list[dict]) -> int:
    """Delete the given entries. Returns how many were removed."""
    if config.TARGET_CALENDAR_ID == "primary":
        raise RuntimeError(
            "Refusing to bulk-delete from your primary calendar. "
            "Point CALASSIST_CALENDAR_ID at the CalAssist calendar first."
        )
    service = build("calendar", "v3", credentials=get_credentials())
    removed = 0
    for e in events:
        service.events().delete(
            calendarId=config.TARGET_CALENDAR_ID, eventId=e["id"]
        ).execute()
        removed += 1
    return removed


def describe(event: dict) -> str:
    when = event["start"].get("dateTime", event["start"].get("date", ""))
    return f"{when[:10]} {when[11:16]}  {event.get('summary', '')}"
