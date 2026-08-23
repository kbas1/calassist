"""Tools the agent may call.

Every tool here is READ-ONLY except submit_proposal, which only records a
proposal in memory. Nothing in this file touches your calendar. Writing
happens in writer.py, after you approve.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from anthropic import beta_tool

import config
from src.availability import find_free_slots
from src.calendar_read import fetch_all_events, is_busy
from src.priorities_read import (extract_defaults, extract_week_section,
                                 fetch_priorities, week_label)
from src.timefmt import span_12h

TIME_RE = re.compile(r"^\d{2}:\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_KEYS = ["blocks", "skipped_already_scheduled", "not_scheduled", "warnings"]
BLOCK_KEYS = ["title", "day", "start", "end", "reason", "category"]


@dataclass
class Proposal:
    blocks: list = field(default_factory=list)
    skipped_already_scheduled: list = field(default_factory=list)
    not_scheduled: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# The agent's proposal lands here. main.py reads it after the run.
CAPTURED: dict = {"proposal": None}


def validate_proposal(payload: dict) -> list[str]:
    """Return human-readable problems with a proposal. Empty list means valid."""
    errors = []
    for key in REQUIRED_KEYS:
        if key not in payload:
            errors.append(f"missing required key: {key}")
    if errors:
        return errors

    for i, block in enumerate(payload["blocks"]):
        missing = [k for k in BLOCK_KEYS if k not in block]
        if missing:
            errors.extend(f"block {i} is missing '{k}'" for k in missing)
            continue
        if not DATE_RE.match(block["day"]):
            errors.append(f"block {i} day '{block['day']}' must be YYYY-MM-DD")
        for key in ("start", "end"):
            if not TIME_RE.match(block[key]):
                errors.append(f"block {i} {key} '{block[key]}' must be HH:MM 24-hour")
        if TIME_RE.match(block["start"]) and TIME_RE.match(block["end"]):
            if block["end"] <= block["start"]:
                errors.append(
                    f"block {i} end {block['end']} is at or before start {block['start']}"
                )
        if block["category"] not in config.CATEGORIES:
            errors.append(
                f"block {i} category '{block['category']}' is not one of "
                f"{', '.join(config.CATEGORIES)}"
            )

    return errors


@beta_tool
def get_priorities() -> str:
    """Read this week's priorities, to-dos, and notes.

    Returns only the section for the week being planned; older weeks in the
    file are ignored.
    """
    text = fetch_priorities()
    label = week_label()
    defaults = extract_defaults(text)
    section = extract_week_section(text, label)
    if section:
        return f"{defaults}\n\n{section}" if defaults else section
    return (
        f"No '## Week of {label}' section exists yet. Ask the user what they want "
        f"to accomplish this week. Full file follows for context:\n\n{text}"
    )


@beta_tool
def get_calendar_events(start_date: str, end_date: str) -> str:
    """Read existing calendar commitments for a date range.

    Args:
        start_date: First day to read, as YYYY-MM-DD.
        end_date: Last day to read, as YYYY-MM-DD.
    """
    start = datetime.fromisoformat(start_date).replace(tzinfo=config.TIMEZONE)
    end = datetime.fromisoformat(end_date).replace(tzinfo=config.TIMEZONE) + timedelta(days=1)
    events = fetch_all_events(start, end)

    if not events:
        return "No events in that range."

    lines = []
    for e in events:
        tags = []
        if e.all_day:
            tags.append("ALL-DAY - ask the user whether that day is usable")
        if e.recurring:
            tags.append("recurring")
        if not is_busy(e):
            tags.append("DECLINED - this time is actually free")
        suffix = f"  [{', '.join(tags)}]" if tags else ""
        when = (f"{e.start:%a %Y-%m-%d} "
                f"{span_12h(f'{e.start:%H:%M}', f'{e.end:%H:%M}')}")
        lines.append(f"{when}  {e.summary}{suffix}")
        if e.location:
            lines.append(f"        location: {e.location}")
        if e.description:
            note = " ".join(e.description.split())[:200]
            lines.append(f"        notes: {note}")
    return "\n".join(lines)


@beta_tool
def find_free_slots_tool(start_date: str, end_date: str, minimum_minutes: int,
                         include_overflow: bool = False) -> str:
    """Find bookable gaps, already accounting for work hours and buffers.

    Work hours (weekdays 08:30-17:00) are never returned - the user is at the
    office and that calendar is not visible to you. Use this rather than
    reasoning about gaps yourself.

    Args:
        start_date: First day to search, as YYYY-MM-DD.
        end_date: Last day to search, as YYYY-MM-DD.
        minimum_minutes: Only return gaps at least this long.
        include_overflow: Set true ONLY if the week does not fit in preferred
            hours. Adds weekday 07:00-08:30 and 21:00-22:00. Any block placed
            in an overflow slot must be mentioned in warnings.
    """
    start = datetime.fromisoformat(start_date).replace(tzinfo=config.TIMEZONE)
    end = datetime.fromisoformat(end_date).replace(tzinfo=config.TIMEZONE) + timedelta(days=1)
    events = fetch_all_events(start, end)

    slots = find_free_slots(
        events, start.date(), end.date() - timedelta(days=1),
        minimum_minutes, include_overflow,
    )
    if not slots:
        return f"No free slots of at least {minimum_minutes} minutes."

    lines = []
    for s in slots:
        mins = int((s.end - s.start).total_seconds() // 60)
        tag = "  [OVERFLOW - warn the user if you use this]" if s.is_overflow else ""
        lines.append(f"{s.start:%a %Y-%m-%d} "
                     f"{span_12h(f'{s.start:%H:%M}', f'{s.end:%H:%M}')}"
                     f"  ({mins} min){tag}")
    return "\n".join(lines)


@beta_tool
def submit_proposal(proposal_json: str) -> str:
    """Submit the finished week. Call this exactly once, when ready.

    Args:
        proposal_json: A JSON object with exactly these four keys:
            blocks: list of {title, day (YYYY-MM-DD), start (HH:MM),
                end (HH:MM), reason, category}
                category must be one of: focus, social, workout, errand, travel
            skipped_already_scheduled: list of {item, matched}
            not_scheduled: list of {item, why}
            warnings: list of strings
    """
    try:
        payload = json.loads(proposal_json)
    except json.JSONDecodeError as exc:
        return f"That was not valid JSON ({exc}). Please resend."

    errors = validate_proposal(payload)
    if errors:
        return "Proposal rejected. Fix these and resend:\n- " + "\n- ".join(errors)

    CAPTURED["proposal"] = Proposal(**payload)
    return "Proposal accepted. Stop here - do not call any more tools."


ALL_TOOLS = [get_priorities, get_calendar_events, find_free_slots_tool, submit_proposal]
