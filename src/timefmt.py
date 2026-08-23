"""Human-facing time formatting.

The proposal JSON and the Google Calendar API both use 24-hour HH:MM — that
stays. This is only for anything a person reads.
"""


def to_12h(hhmm: str) -> str:
    """'17:00' -> '5:00 PM'.  '09:30' -> '9:30 AM'."""
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    suffix = "AM" if h < 12 else "PM"
    return f"{h % 12 or 12}:{m:02d} {suffix}"


def span_12h(start: str, end: str) -> str:
    """'17:00','18:30' -> '5:00-6:30 PM'; drops a repeated meridiem."""
    a, b = to_12h(start), to_12h(end)
    if a[-2:] == b[-2:]:
        return f"{a[:-3]}-{b}"
    return f"{a}-{b}"
