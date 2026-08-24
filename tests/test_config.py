from datetime import time

import config


def test_weekday_blocked_ends_where_bookable_begins():
    """Work must end exactly when evening booking starts — no gap, no overlap."""
    _, blocked_end = config.WEEKDAY_BLOCKED
    first_bookable_start, _ = config.WEEKDAY_BOOKABLE[0]
    assert blocked_end == first_bookable_start


def test_overflow_windows_do_not_intrude_on_work():
    """Early-morning overflow must finish before the commute starts."""
    blocked_start, _ = config.WEEKDAY_BLOCKED
    for _, overflow_end in config.WEEKDAY_OVERFLOW:
        assert overflow_end <= blocked_start


def test_buffer_is_not_negative():
    """0 is the intended default — travel blocks replaced the buffer."""
    assert config.BUFFER_MINUTES >= 0


def test_calassist_calendar_is_always_readable():
    """It must see its own blocks, or it will schedule on top of them."""
    assert config.TARGET_CALENDAR_ID in config.READ_CALENDAR_IDS


def test_read_calendars_has_no_blanks():
    assert all(c.strip() for c in config.READ_CALENDAR_IDS)
