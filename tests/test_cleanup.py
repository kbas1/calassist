import pytest

import config
from src.cleanup import delete_blocks, describe, find_written_blocks


def test_refuses_to_bulk_delete_from_primary(monkeypatch):
    """The one mistake that would be unrecoverable."""
    monkeypatch.setattr(config, "TARGET_CALENDAR_ID", "primary")
    with pytest.raises(RuntimeError, match="primary"):
        delete_blocks([{"id": "anything"}])


def test_describe_renders_a_readable_line():
    e = {"start": {"dateTime": "2026-08-24T17:00:00-04:00"}, "summary": "Gym"}
    assert describe(e) == "2026-08-24 17:00  Gym"


def test_only_calassist_written_blocks_are_selected(monkeypatch):
    raw = [
        {"id": "1", "summary": "Mine", "description": "Scheduled by CalAssist.\n\nWhy: x"},
        {"id": "2", "summary": "Yours", "description": "Dinner with Sam"},
        {"id": "3", "summary": "Yours too"},                    # no description
    ]

    class FakeEvents:
        def list(self, **kw): return self
        def execute(self): return {"items": raw}

    class FakeService:
        def events(self): return FakeEvents()

    monkeypatch.setattr("src.cleanup.build", lambda *a, **k: FakeService())
    monkeypatch.setattr("src.cleanup.get_credentials", lambda: None)
    from datetime import datetime
    picked = find_written_blocks(datetime.now(config.TIMEZONE), datetime.now(config.TIMEZONE))
    assert [e["id"] for e in picked] == ["1"]
