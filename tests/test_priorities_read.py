from src.priorities_read import extract_week_section

DOC = """# Planning

## Week of 8.17
### Priorities
1. Old thing - 2h

## Week of 8.24
### Priorities
1. NVIDIA interview prep - 4h
2. Q4 roadmap draft - 3h

### Already scheduled
- Dentist - Tue 2pm

## Week of 8.31
### Priorities
1. Future thing - 1h
"""


def test_extracts_only_the_requested_week():
    section = extract_week_section(DOC, "8.24")
    assert "NVIDIA interview prep" in section
    assert "Old thing" not in section
    assert "Future thing" not in section


def test_includes_all_subsections_of_that_week():
    section = extract_week_section(DOC, "8.24")
    assert "Already scheduled" in section
    assert "Dentist" in section


def test_returns_none_when_week_absent():
    assert extract_week_section(DOC, "9.14") is None


# --- which week are we planning? -------------------------------------

from datetime import date

from src.priorities_read import target_monday, week_label


def test_sunday_plans_the_week_ahead():
    """The Sunday-evening ritual: plan the week that starts tomorrow."""
    sunday = date(2026, 8, 23)
    assert target_monday(sunday) == date(2026, 8, 24)
    assert week_label(sunday) == "8.24"


def test_saturday_plans_the_week_ahead():
    saturday = date(2026, 8, 22)
    assert target_monday(saturday) == date(2026, 8, 24)


def test_midweek_plans_the_current_week():
    """On Wednesday you're adjusting this week, not next."""
    wednesday = date(2026, 8, 26)
    assert target_monday(wednesday) == date(2026, 8, 24)
    assert week_label(wednesday) == "8.24"


def test_monday_plans_that_same_week():
    monday = date(2026, 8, 24)
    assert target_monday(monday) == date(2026, 8, 24)
