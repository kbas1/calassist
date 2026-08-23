"""CalAssist CLI.

    python -m src.main plan              propose only, write nothing
    python -m src.main plan --write      propose, then ask before writing
"""
import argparse
import sys
from datetime import date, datetime, timedelta

import config
from src.agent import opening_message, run_conversation
from src.calendar_read import fetch_events
from src.preview import render
from src.priorities_read import target_monday
from src.writer import create_events


def _monday(week_arg: str | None) -> date:
    return datetime.fromisoformat(week_arg).date() if week_arg else target_monday()


def main() -> int:
    parser = argparse.ArgumentParser(prog="calassist")
    parser.add_argument("command", choices=["plan"])
    parser.add_argument("--write", action="store_true",
                        help="offer to create the events (default is preview only)")
    parser.add_argument("--week", help="Monday of the target week, YYYY-MM-DD")
    args = parser.parse_args()

    monday = _monday(args.week)
    sunday = monday + timedelta(days=6)
    print(f"CalAssist — planning {monday:%b %-d} to {sunday:%b %-d}")
    print(f"Type your answers, or 'quit' to stop. Nothing is written without asking.\n")

    proposal = run_conversation(opening_message(monday))
    if proposal is None:
        print("\nNo proposal made. Nothing was changed.")
        return 1

    start = datetime.combine(monday, datetime.min.time(), tzinfo=config.TIMEZONE)
    existing = fetch_events(start, start + timedelta(days=7))
    path = render(proposal, existing)

    print("\n" + "=" * 64)
    for b in sorted(proposal.blocks, key=lambda x: (x["day"], x["start"])):
        day = datetime.fromisoformat(b["day"]).date()
        print(f"  {day:%a %m/%d}  {b['start']}-{b['end']}  "
              f"[{b['category']}]  {b['title']}")
    for s in proposal.skipped_already_scheduled:
        print(f"  skipped (already on calendar): {s['item']}")
    for n in proposal.not_scheduled:
        print(f"  DID NOT FIT: {n['item']} — {n['why']}")
    for w in proposal.warnings:
        print(f"  warning: {w}")
    print(f"\n  Visual preview:  file://{path}")
    print("=" * 64 + "\n")

    if not args.write:
        print("Preview only — nothing written. Re-run with --write to create these.")
        return 0

    answer = input(f"Write {len(proposal.blocks)} events to your "
                   f"CalAssist calendar? [y/N] ").strip().lower()
    if answer != "y":
        print("Nothing written.")
        return 0

    result = create_events(proposal)
    for title in result.created:
        print(f"  created: {title}")
    for title, err in result.failed:
        print(f"  FAILED:  {title} — {err}")

    if result.failed:
        print(f"\n{len(result.created)} created, {len(result.failed)} failed.")
        return 1
    print(f"\n{len(result.created)} events created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
