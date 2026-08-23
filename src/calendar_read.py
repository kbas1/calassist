"""Read events from Google Calendar."""
from dataclasses import dataclass
from datetime import datetime

from googleapiclient.discovery import build

import config
from src.auth import get_credentials

# Attendee response statuses that still consume your time.
# "declined" is deliberately absent — you said no, so that time is free.
BUSY_STATUSES = {"accepted", "tentative", "needsAction", ""}


@dataclass
class Event:
    summary: str
    start: datetime
    end: datetime
    all_day: bool
    recurring: bool
    response_status: str
    location: str = ""
    description: str = ""


def is_busy(event: Event) -> bool:
    """Does this event actually consume time?

    Declined meetings do not — that time is free even though the event
    is still sitting on the calendar.
    """
    return event.response_status in BUSY_STATUSES


def _my_response(raw: dict) -> str:
    """This account's RSVP, or '' for events with no attendee list."""
    for attendee in raw.get("attendees", []):
        if attendee.get("self"):
            return attendee.get("responseStatus", "")
    return ""


def _parse_when(raw_side: dict) -> tuple[datetime, bool]:
    """Return (timezone-aware datetime, is_all_day) for a start/end block.

    All-day events come back as a bare date. We attach the configured
    timezone so every datetime in the system is aware — mixing naive and
    aware datetimes raises TypeError on comparison, which would blow up
    the free-slot arithmetic.
    """
    if "date" in raw_side:
        naive = datetime.fromisoformat(raw_side["date"])
        return naive.replace(tzinfo=config.TIMEZONE), True
    return datetime.fromisoformat(raw_side["dateTime"]), False


def fetch_all_events(start: datetime, end: datetime) -> list[Event]:
    """Every event that occupies this time, across all calendars we care about.

    CalAssist writes to TARGET_CALENDAR_ID but the user lives on `primary`.
    Reading only `primary` would make CalAssist blind to blocks it wrote on a
    previous run, and it would cheerfully schedule on top of them.
    """
    ids = ["primary"]
    if config.TARGET_CALENDAR_ID not in ids:
        ids.append(config.TARGET_CALENDAR_ID)

    events: list[Event] = []
    for cid in ids:
        events.extend(fetch_events(start, end, calendar_id=cid))
    return sorted(events, key=lambda e: e.start)


def fetch_events(start: datetime, end: datetime, calendar_id: str = "primary") -> list[Event]:
    """Fetch events between two timezone-aware datetimes, expanding recurrences."""
    service = build("calendar", "v3", credentials=get_credentials())
    raw_events = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,       # expand recurring series into instances
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )

    events = []
    for raw in raw_events:
        start_dt, all_day = _parse_when(raw["start"])
        end_dt, _ = _parse_when(raw["end"])
        events.append(
            Event(
                summary=raw.get("summary", "(no title)"),
                start=start_dt,
                end=end_dt,
                all_day=all_day,
                recurring="recurringEventId" in raw,
                response_status=_my_response(raw),
                location=raw.get("location") or "",
                description=raw.get("description") or "",
            )
        )
    return events
