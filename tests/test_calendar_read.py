from datetime import datetime
from zoneinfo import ZoneInfo

from src.calendar_read import Event, is_busy

TZ = ZoneInfo("America/New_York")


def _event(**kwargs):
    defaults = dict(
        summary="Meeting",
        start=datetime(2026, 8, 25, 10, 0, tzinfo=TZ),
        end=datetime(2026, 8, 25, 11, 0, tzinfo=TZ),
        all_day=False,
        recurring=False,
        response_status="accepted",
    )
    defaults.update(kwargs)
    return Event(**defaults)


def test_accepted_meeting_is_busy():
    assert is_busy(_event(response_status="accepted")) is True


def test_declined_meeting_is_free():
    """You said no. That time is yours."""
    assert is_busy(_event(response_status="declined")) is False


def test_tentative_meeting_is_busy():
    """Might happen — don't double-book against it."""
    assert is_busy(_event(response_status="tentative")) is True


def test_event_with_no_response_status_is_busy():
    """Events you created yourself have no attendee status."""
    assert is_busy(_event(response_status="")) is True
