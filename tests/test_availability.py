from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.availability import bookable_windows, find_free_slots, merge_intervals
from src.calendar_read import Event

TZ = ZoneInfo("America/New_York")
MONDAY = date(2026, 8, 24)
SATURDAY = date(2026, 8, 29)


def dt(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ)


def busy(d: date, start_h: int, end_h: int, **kw) -> Event:
    defaults = dict(
        summary="Thing", all_day=False, recurring=False, response_status="accepted"
    )
    defaults.update(kw)
    return Event(start=dt(d, start_h), end=dt(d, end_h), **defaults)


# --- merge_intervals -------------------------------------------------

def test_merge_leaves_disjoint_intervals_alone():
    a = (dt(MONDAY, 17), dt(MONDAY, 18))
    b = (dt(MONDAY, 19), dt(MONDAY, 20))
    assert merge_intervals([a, b]) == [a, b]


def test_merge_combines_overlapping_intervals():
    a = (dt(MONDAY, 17), dt(MONDAY, 19))
    b = (dt(MONDAY, 18), dt(MONDAY, 20))
    assert merge_intervals([a, b]) == [(dt(MONDAY, 17), dt(MONDAY, 20))]


def test_merge_combines_touching_intervals():
    a = (dt(MONDAY, 17), dt(MONDAY, 18))
    b = (dt(MONDAY, 18), dt(MONDAY, 19))
    assert merge_intervals([a, b]) == [(dt(MONDAY, 17), dt(MONDAY, 19))]


# --- bookable_windows ------------------------------------------------

def test_weekday_window_is_evening_only():
    assert bookable_windows(MONDAY, include_overflow=False) == [
        (dt(MONDAY, 17), dt(MONDAY, 21))
    ]


def test_weekend_window_is_all_day():
    assert bookable_windows(SATURDAY, include_overflow=False) == [
        (dt(SATURDAY, 9), dt(SATURDAY, 21))
    ]


def test_overflow_adds_early_morning_and_late_evening_on_weekdays():
    windows = bookable_windows(MONDAY, include_overflow=True)
    assert (dt(MONDAY, 7), dt(MONDAY, 8, 30)) in windows
    assert (dt(MONDAY, 21), dt(MONDAY, 22)) in windows


# --- find_free_slots -------------------------------------------------

def test_empty_calendar_gives_whole_evening():
    slots = find_free_slots([], MONDAY, MONDAY, minimum_minutes=60)
    assert slots == [(dt(MONDAY, 17), dt(MONDAY, 21), False)]


def test_work_hours_are_never_offered():
    """The whole point: 10am Monday looks empty but you're at the office."""
    slots = find_free_slots([], MONDAY, MONDAY, minimum_minutes=60)
    for start, _, _ in slots:
        assert start.hour >= 17


def test_event_splits_the_evening_with_no_idle_gap():
    """A 6-7pm event leaves 5:00-6:00 and 7:00-9:00 — slots touch the event.

    BUFFER_MINUTES is 0 by design: travel is an explicit block, so a buffer
    would only manufacture dead time between things that should be contiguous.
    """
    slots = find_free_slots([busy(MONDAY, 18, 19)], MONDAY, MONDAY, minimum_minutes=30)
    assert slots == [
        (dt(MONDAY, 17), dt(MONDAY, 18), False),
        (dt(MONDAY, 19), dt(MONDAY, 21), False),
    ]


def test_slots_shorter_than_minimum_are_dropped():
    """Same 6-7pm event. The gaps are 60 min and 120 min.

    Asking for 90 keeps only the later one — the 60-min sliver is dropped.
    """
    slots = find_free_slots([busy(MONDAY, 18, 19)], MONDAY, MONDAY, minimum_minutes=90)
    assert slots == [(dt(MONDAY, 19), dt(MONDAY, 21), False)]


def test_nothing_qualifies_when_minimum_exceeds_every_gap():
    """Asking for 3 hours when the largest gap is 2 hours."""
    slots = find_free_slots([busy(MONDAY, 18, 19)], MONDAY, MONDAY, minimum_minutes=180)
    assert slots == []


def test_declined_event_does_not_block_time():
    events = [busy(MONDAY, 18, 19, response_status="declined")]
    slots = find_free_slots(events, MONDAY, MONDAY, minimum_minutes=60)
    assert slots == [(dt(MONDAY, 17), dt(MONDAY, 21), False)]


def test_full_evening_leaves_nothing():
    slots = find_free_slots([busy(MONDAY, 17, 21)], MONDAY, MONDAY, minimum_minutes=30)
    assert slots == []


def test_overflow_slots_are_flagged():
    slots = find_free_slots(
        [busy(MONDAY, 17, 21)], MONDAY, MONDAY, minimum_minutes=60, include_overflow=True
    )
    assert len(slots) > 0
    assert all(slot.is_overflow for slot in slots)
