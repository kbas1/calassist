from src.tools import validate_proposal


def _payload(blocks):
    return {
        "blocks": blocks,
        "skipped_already_scheduled": [],
        "not_scheduled": [],
        "warnings": [],
    }


GOOD_BLOCK = {
    "title": "Prep", "day": "2026-08-25",
    "start": "17:00", "end": "19:00", "reason": "first clear evening",
    "category": "focus",
}


def test_valid_proposal_has_no_errors():
    assert validate_proposal(_payload([GOOD_BLOCK])) == []


def test_empty_proposal_is_valid():
    """A week where nothing needed scheduling is legitimate."""
    assert validate_proposal(_payload([])) == []


def test_missing_top_level_key_is_reported():
    errors = validate_proposal({"blocks": []})
    assert any("skipped_already_scheduled" in e for e in errors)


def test_block_missing_a_field_is_reported():
    bad = {k: v for k, v in GOOD_BLOCK.items() if k != "end"}
    assert any("end" in e for e in validate_proposal(_payload([bad])))


def test_bad_time_format_is_reported():
    bad = {**GOOD_BLOCK, "start": "5pm"}
    assert any("5pm" in e for e in validate_proposal(_payload([bad])))


def test_bad_date_format_is_reported():
    bad = {**GOOD_BLOCK, "day": "08/25/2026"}
    assert any("08/25/2026" in e for e in validate_proposal(_payload([bad])))


def test_end_before_start_is_reported():
    bad = {**GOOD_BLOCK, "start": "19:00", "end": "17:00"}
    assert any("before" in e.lower() for e in validate_proposal(_payload([bad])))


def test_zero_length_block_is_reported():
    bad = {**GOOD_BLOCK, "start": "17:00", "end": "17:00"}
    assert validate_proposal(_payload([bad])) != []


def test_unknown_category_is_reported():
    bad = {**GOOD_BLOCK, "category": "deep-work"}
    assert any("deep-work" in e for e in validate_proposal(_payload([bad])))


def test_missing_category_is_reported():
    bad = {k: v for k, v in GOOD_BLOCK.items() if k != "category"}
    assert any("category" in e for e in validate_proposal(_payload([bad])))


def test_every_configured_category_is_accepted():
    import config
    for cat in config.CATEGORIES:
        assert validate_proposal(_payload([{**GOOD_BLOCK, "category": cat}])) == []
