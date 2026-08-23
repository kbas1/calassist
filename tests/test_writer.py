import config
from src.writer import to_google_event

BLOCK = {
    "title": "Interview prep", "day": "2026-08-25",
    "start": "17:00", "end": "19:00",
    "reason": "first clear evening", "category": "focus",
}


def test_block_becomes_a_google_event_with_timezone():
    e = to_google_event(BLOCK)
    assert e["summary"] == "Interview prep"
    assert e["start"]["dateTime"].startswith("2026-08-25T17:00")
    assert e["end"]["dateTime"].startswith("2026-08-25T19:00")
    assert e["start"]["timeZone"] == "America/New_York"


def test_reason_is_carried_into_the_description():
    assert "first clear evening" in to_google_event(BLOCK)["description"]


def test_category_sets_the_calendar_colour():
    assert to_google_event(BLOCK)["colorId"] == config.CATEGORY_COLORS["focus"]


def test_each_category_maps_to_its_own_colour():
    seen = {}
    for cat in config.CATEGORIES:
        cid = to_google_event({**BLOCK, "category": cat})["colorId"]
        assert cid not in seen, f"{cat} and {seen[cid]} share colour {cid}"
        seen[cid] = cat


def test_travel_blocks_are_graphite():
    """Travel is overhead — it should read as muted, not as a commitment."""
    e = to_google_event({**BLOCK, "category": "travel", "title": "Travel home"})
    assert e["colorId"] == "8"


def test_unknown_category_falls_back_rather_than_crashing():
    """A bad category should never block a write — validation catches it earlier."""
    e = to_google_event({**BLOCK, "category": "nonsense"})
    assert "colorId" not in e or e["colorId"] is not None
