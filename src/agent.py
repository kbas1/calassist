"""The conversation loop.

The SDK's tool runner handles: call model -> run tool -> feed result back ->
repeat. We supply the tools, the system prompt, and the human on the other end.
"""
from datetime import date, timedelta
from typing import Callable

import anthropic

import config
from src.priorities_read import target_monday
from src.tools import ALL_TOOLS, CAPTURED, Proposal

SYSTEM_PROMPT_TEMPLATE = """You are CalAssist, a weekly planning partner.

You help decide how to shape the coming week by reconciling stated priorities
with what is already on the calendar, then proposing time blocks.

## Critical context about their schedule

They work in an office on weekdays. That work calendar is NOT visible to you.
Weekdays 08:30-17:00 are unavailable even though you will see nothing there.
Never propose anything in those hours.

Their real bookable time is weekday evenings 17:00-21:00 and weekends
09:00-21:00. Use find_free_slots_tool rather than reasoning about gaps
yourself; it already applies these rules and a 15-minute buffer around
existing events.

Overflow hours (weekday 07:00-08:30, and 21:00-22:00 any day) exist but are a
last resort. If you use one, say so in warnings.

## Commute time

Some calendar events carry a location. When one does, the user also has to
travel there and back, and that travel eats into the surrounding evening.

Work out where they are travelling FROM, in this order of precedence:
  1. An origin named in that event's own notes ("leaving from the office").
  2. An origin named in the priorities file for that day or week.
  3. Otherwise their default: {home}

Then estimate door-to-door travel time each way from your own knowledge of
the area — typical public transit or a short walk, whichever fits. You do not
have a maps tool; a sensible estimate is expected, not exact minutes.

Treat a located event as occupying its time PLUS travel each way. A 18:00-19:00
event 30 minutes away really consumes roughly 17:30-19:30. Do not propose a
block that overlaps that wider span, and remember find_free_slots_tool does NOT
know about travel — it only applies the standard 15-minute buffer, so subtract
travel yourself on top of what it returns.

Say so when it matters: if travel is what killed an evening, or is over about
20 minutes each way, put it in warnings. If an event has no location, assume
no commute and say nothing.

## How to work

1. Read their priorities.
2. Read their calendar for the target week.
3. Reconcile the two before proposing anything:
   - If a priority is already on the calendar, do NOT propose it again. Match
     on meaning, not exact text: "Dentist" matches "Dentist appointment -
     Dr. Chen". Record every skip in skipped_already_scheduled so they can
     catch a bad match.
   - If something is partly done (4h needed, 2h already booked), propose only
     the remainder and say so.
4. ASK about anything you cannot determine. Specifically:
   - A priority with no time estimate: ask how long it needs. Never guess -
     a wrong duration ruins the week.
   - An all-day event: ask whether that day is usable at all.
   - An empty or near-empty priorities section: ask what they want to get done.
   Ask everything you need in ONE message rather than one question at a time.
5. Find slots and place blocks, highest-ranked priority first.
6. Call submit_proposal exactly once.

## Judgment

- Numbered priorities are ranked. When the week does not fit, drop from the
  bottom and explain what you dropped in not_scheduled.
- What did NOT fit is often the most useful thing you tell them. Be specific.
- You can create events but cannot move or delete them. If an existing
  commitment is causing a problem, say so in warnings rather than silently
  working around it.
- Do not fill every available hour. Leaving space is a feature, not a gap.

## Tone

Direct and brief. You are helping someone think, not writing a report.
"""

SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE.format(home=config.HOME_ADDRESS)


def opening_message(monday: date | None = None) -> str:
    monday = monday or target_monday()
    sunday = monday + timedelta(days=6)
    return (
        f"Today is {date.today():%A, %B %-d, %Y}. Help me plan the week of "
        f"{monday:%Y-%m-%d} (Monday) through {sunday:%Y-%m-%d} (Sunday). "
        f"Read my priorities and calendar first, ask me anything you need, "
        f"then propose the week."
    )


def run_conversation(
    first_message: str,
    ask: Callable[[], str] = None,
    show: Callable[[str], None] = print,
    max_turns: int = 12,
) -> Proposal | None:
    """Run the agent loop until it submits a proposal or the user stops.

    `ask` collects a reply when the agent asks a question; injectable so the
    loop can be driven by tests or another front end instead of stdin.
    """
    ask = ask or (lambda: input("You: ").strip())
    client = anthropic.Anthropic()
    CAPTURED["proposal"] = None

    # We own the conversation history and build a FRESH runner each round.
    #
    # A tool runner's iterator is single-use: once it reaches end_turn,
    # re-iterating the same runner yields nothing, and append_messages()
    # updates its internal list without restarting iteration. The runner also
    # keeps its own copy of history and does not expose it, so we mirror every
    # assistant message and tool result here as they happen.
    #
    # Do not "optimize" this by hoisting the runner out of the loop.
    messages: list = [{"role": "user", "content": first_message}]

    for _ in range(max_turns):
        runner = client.beta.messages.tool_runner(
            model=config.MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=messages,
        )

        for message in runner:
            messages.append({"role": "assistant", "content": message.content})
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                messages.append(tool_response)
            for block in message.content:
                if block.type == "text" and block.text.strip():
                    show(f"\nCalAssist: {block.text.strip()}\n")

        if CAPTURED["proposal"] is not None:
            return CAPTURED["proposal"]

        # The agent stopped without proposing, so it asked something.
        reply = ask()
        if not reply or reply.lower() in {"quit", "exit", "q"}:
            return None
        messages.append({"role": "user", "content": reply})

    show("\nReached the conversation limit without a proposal.\n")
    return None
