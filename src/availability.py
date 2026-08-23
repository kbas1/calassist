"""Find bookable gaps.

Deterministic interval arithmetic. The model never does this — LLMs are
unreliable at arithmetic and excellent at judgment, so code finds the gaps
and the model decides what belongs in them.
"""
from datetime import date, datetime, time, timedelta
from typing import NamedTuple

import config
from src.calendar_read import Event, is_busy


class Slot(NamedTuple):
    start: datetime
    end: datetime
    is_overflow: bool


def _at(day: date, t: time) -> datetime:
    return datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=config.TIMEZONE)


def merge_intervals(
    intervals: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """Collapse overlapping or touching intervals into the fewest possible."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:                       # overlaps or touches
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def bookable_windows(day: date, include_overflow: bool) -> list[tuple[datetime, datetime]]:
    """The windows we may schedule in on this day, before subtracting events.

    Work hours never appear here — they are excluded by construction, not by
    checking events, because the work calendar is invisible to this app.
    """
    is_weekend = day.weekday() >= 5
    base = config.WEEKEND_BOOKABLE if is_weekend else config.WEEKDAY_BOOKABLE
    windows = [(_at(day, s), _at(day, e)) for s, e in base]

    if include_overflow:
        extra = list(config.EVENING_OVERFLOW)
        if not is_weekend:
            extra += config.WEEKDAY_OVERFLOW
        windows += [(_at(day, s), _at(day, e)) for s, e in extra]

    return sorted(windows)


def find_free_slots(
    events: list[Event],
    start_date: date,
    end_date: date,
    minimum_minutes: int,
    include_overflow: bool = False,
) -> list[Slot]:
    """Bookable gaps of at least `minimum_minutes`, buffered away from events."""
    buffer = timedelta(minutes=config.BUFFER_MINUTES)
    minimum = timedelta(minutes=minimum_minutes)

    # Expand each busy event by the buffer on both sides, then merge so
    # overlapping meetings don't produce phantom slivers between them.
    blocked = merge_intervals(
        [(e.start - buffer, e.end + buffer) for e in events if is_busy(e)]
    )

    slots: list[Slot] = []
    day = start_date
    while day <= end_date:
        preferred = set(bookable_windows(day, include_overflow=False))
        for window_start, window_end in bookable_windows(day, include_overflow):
            is_overflow = (window_start, window_end) not in preferred
            cursor = window_start
            for busy_start, busy_end in blocked:
                if busy_end <= cursor or busy_start >= window_end:
                    continue                        # no intersection
                if busy_start - cursor >= minimum:
                    slots.append(Slot(cursor, busy_start, is_overflow))
                cursor = max(cursor, busy_end)
            if window_end - cursor >= minimum:
                slots.append(Slot(cursor, window_end, is_overflow))
        day += timedelta(days=1)

    return sorted(slots)
