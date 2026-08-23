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
