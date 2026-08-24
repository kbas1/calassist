"""CalAssist CLI.

    python -m src.main plan              propose and revise; write nothing
    python -m src.main plan --write      same, then ask before creating events
"""
import argparse
import sys
import webbrowser
from datetime import date, datetime, timedelta

import config
from src.agent import opening_message, run_conversation
from src.calendar_read import fetch_all_events
from src.cleanup import delete_blocks, describe, find_written_blocks
from src.preview import render
from src.priorities_read import target_monday
from src.confirm import is_acceptance
from src.timefmt import span_12h
from src.tools import Proposal
from src.writer import create_events


def _monday(week_arg: str | None) -> date:
    return datetime.fromisoformat(week_arg).date() if week_arg else target_monday()


def _summarise(proposal: Proposal, path: str) -> None:
    print("\n" + "=" * 64)
    for b in sorted(proposal.blocks, key=lambda x: (x["day"], x["start"])):
        day = datetime.fromisoformat(b["day"]).date()
        print(f"  {day:%a %m/%d}  {span_12h(b['start'], b['end']):>16}  "
              f"[{b['category']}]  {b['title']}")
    for s in proposal.skipped_already_scheduled:
        print(f"  skipped (already on calendar): {s['item']}")
    for n in proposal.not_scheduled:
        print(f"  DID NOT FIT: {n['item']} — {n['why']}")
    for w in proposal.warnings:
        print(f"  warning: {w}")
    print(f"\n  Visual preview (opening in your browser):\n    file://{path}")
    print("=" * 64)


def main() -> int:
    parser = argparse.ArgumentParser(prog="calassist")
    parser.add_argument("command", choices=["plan", "clear"])
    parser.add_argument("--write", action="store_true",
                        help="offer to create the events (default is preview only)")
    parser.add_argument("--week", help="Monday of the target week, YYYY-MM-DD")
    parser.add_argument("--no-open", action="store_true",
                        help="do not open the visual preview in a browser")
    args = parser.parse_args()

    monday = _monday(args.week)
    sunday = monday + timedelta(days=6)
    start_dt = datetime.combine(monday, datetime.min.time(), tzinfo=config.TIMEZONE)

    if args.command == "clear":
        found = find_written_blocks(start_dt, start_dt + timedelta(days=7))
        if not found:
            print(f"Nothing to clear for {monday:%b %-d}-{sunday:%b %-d}.")
            return 0
        print(f"These {len(found)} blocks were created by CalAssist:\n")
        for e in found:
            print(f"  {describe(e)}")
        print("\nAnything you created yourself is untouched.")
        if not is_acceptance(input(f"\nDelete these {len(found)}? [yes/no] ").strip()
                             or "no"):
            print("Nothing deleted.")
            return 0
        print(f"\nDeleted {delete_blocks(found)} blocks.")
        return 0

    print(f"CalAssist — planning {monday:%b %-d} to {sunday:%b %-d}")
    print("─" * 64)
    print("You are now talking to CalAssist, not the shell — typed text goes")
    print("to the agent. Type 'quit' to leave. Nothing is written unasked.")
    print("─" * 64)
    print("First reply usually takes 30-60 seconds while it reads your "
          "priorities and calendar.\n")

    start = start_dt

    def on_proposal(proposal: Proposal) -> str | None:
        """Show the week, then accept it or send feedback back to the agent."""
        # Exclude blocks CalAssist wrote on a previous run: the proposal
        # supersedes them, and drawing both stacks a grey copy under every
        # coloured block.
        existing = [e for e in fetch_all_events(start, start + timedelta(days=7))
                    if not e.written_by_calassist]
        path = render(proposal, existing)
        _summarise(proposal, path)
        if not args.no_open:
            webbrowser.open(f"file://{path}")
        print("\n  Type 'yes' to put this on your calendar,")
        print("  or say what to change (e.g. 'move the gym to Tuesday').\n")
        reply = input("  yes / change > ").strip()
        return None if is_acceptance(reply) else reply

    proposal = run_conversation(opening_message(monday), on_proposal=on_proposal)
    if proposal is None:
        print("\nNo proposal accepted. Nothing was changed.")
        return 1

    if not args.write:
        print("\nAccepted — but this was a preview run, so nothing was written.")
        print("Re-run with --write to create these events.")
        return 0

    answer = input(f"\nWrite {len(proposal.blocks)} events to your "
                   f"CalAssist calendar? [yes/no] ").strip()
    if not answer or not is_acceptance(answer):
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
