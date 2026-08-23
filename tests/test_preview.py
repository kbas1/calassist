import os
from datetime import datetime
from zoneinfo import ZoneInfo

from src.calendar_read import Event
from src.preview import render
from src.tools import Proposal

TZ = ZoneInfo("America/New_York")


def _proposal():
    return Proposal(
        blocks=[
            {"title": "Interview prep", "day": "2026-08-27", "start": "17:00",
             "end": "19:00", "reason": "first clear evening", "category": "focus"},
            {"title": "Travel to Pickleball", "day": "2026-08-24", "start": "17:30",
             "end": "18:00", "reason": "FiDi, ~30 min", "category": "travel"},
        ],
        skipped_already_scheduled=[{"item": "Dentist", "matched": "Dentist - Dr. Chen"}],
        not_scheduled=[{"item": "Design review", "why": "no 90-min slot left"}],
        warnings=["Monday is commute-heavy"],
    )


def _existing():
    return [Event(summary="Free Salsa Lesson",
                  start=datetime(2026, 8, 26, 18, 0, tzinfo=TZ),
                  end=datetime(2026, 8, 26, 19, 0, tzinfo=TZ),
                  all_day=False, recurring=False, response_status="accepted",
                  location="Domino Park")]


def test_render_writes_a_file(tmp_path):
    path = render(_proposal(), _existing(), str(tmp_path / "week.html"))
    assert os.path.exists(path)


def test_html_contains_every_section(tmp_path):
    html = open(render(_proposal(), _existing(), str(tmp_path / "w.html"))).read()
    assert "Interview prep" in html            # proposed block
    assert "Travel to Pickleball" in html      # travel block
    assert "Free Salsa Lesson" in html         # existing commitment
    assert "Design review" in html             # did not fit
    assert "Monday is commute-heavy" in html   # warning


def test_categories_get_distinct_css_classes(tmp_path):
    html = open(render(_proposal(), _existing(), str(tmp_path / "w.html"))).read()
    assert "cat-focus" in html
    assert "cat-travel" in html


def test_work_hours_are_shaded(tmp_path):
    html = open(render(_proposal(), _existing(), str(tmp_path / "w.html"))).read()
    assert "work" in html and "Not Visible To CalAssist" in html


def test_times_are_twelve_hour(tmp_path):
    html = open(render(_proposal(), _existing(), str(tmp_path / "w.html"))).read()
    assert "5 PM" in html
    assert ">17<" not in html            # no bare 24-hour labels


def test_title_is_owner_and_week(tmp_path):
    html = open(render(_proposal(), _existing(), str(tmp_path / "w.html"))).read()
    assert "Khushi's Week of Aug-24-2026" in html


def test_notes_replaces_watch_out(tmp_path):
    html = open(render(_proposal(), _existing(), str(tmp_path / "w.html"))).read()
    assert "Notes" in html
    assert "Watch out" not in html


def test_grid_trims_to_the_hours_actually_used(tmp_path):
    """Zoom: do not render a wall of empty 7 AM rows if nothing is there."""
    p = Proposal(blocks=[{"title": "Late thing", "day": "2026-08-27", "start": "20:00",
                          "end": "21:00", "reason": "x", "category": "focus"}])
    html = open(render(p, [], str(tmp_path / "z.html"))).read()
    assert "7 AM" not in html


def test_handles_an_empty_proposal(tmp_path):
    path = render(Proposal(), [], str(tmp_path / "empty.html"))
    assert os.path.exists(path)


def test_skipped_section_is_not_rendered(tmp_path):
    """Deliberately dropped — the user already knows what is on their calendar."""
    html = open(render(_proposal(), _existing(), str(tmp_path / "w.html"))).read()
    assert "Already On Your Calendar" not in html
    assert "Dentist" not in html


def test_block_height_reflects_real_duration(tmp_path):
    """A 30-min block must not paint the same area as a 2-hour one.

    At hour resolution both filled exactly one cell, which made the chart
    misrepresent the shape of the week.
    """
    short = Proposal(blocks=[{"title": "Short", "day": "2026-08-27", "start": "17:00",
                              "end": "17:30", "reason": "x", "category": "errand"}])
    long_ = Proposal(blocks=[{"title": "Long", "day": "2026-08-27", "start": "17:00",
                              "end": "19:00", "reason": "x", "category": "errand"}])
    n_short = open(render(short, [], str(tmp_path / "s.html"))).read().count("cat-errand")
    n_long = open(render(long_, [], str(tmp_path / "l.html"))).read().count("cat-errand")
    assert n_long == n_short * 4, f"2h should be 4x a 30m block, got {n_long} vs {n_short}"


def test_quarter_hour_starts_are_honoured(tmp_path):
    """17:45-18:30 must start three quarters into the 5 PM hour."""
    p = Proposal(blocks=[{"title": "Odd", "day": "2026-08-27", "start": "17:45",
                          "end": "18:30", "reason": "x", "category": "focus"}])
    html = open(render(p, [], str(tmp_path / "q.html"))).read()
    assert html.count("cat-focus") == 3          # 45 min = 3 quarter-hour slots


def test_title_uses_lowercase_of(tmp_path):
    html = open(render(_proposal(), _existing(), str(tmp_path / "t.html"))).read()
    assert "Week of Aug-24-2026" in html
    assert "Week Of" not in html
