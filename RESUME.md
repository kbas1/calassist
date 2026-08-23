# CalAssist — paused 2026-08-23 (evening)

## Run it

    source ~/.zshrc     # once per terminal window, first time only
    calassist           # plan the week, asks before writing
    calassist-preview   # same, never writes
    calweek             # reopen the last chart

## State

36 commits, 131 tests passing, published at github.com/kbas1/calassist.
CalAssist calendar is EMPTY — the test week was deleted deliberately so the
next run starts clean. Your own 7 commitments are untouched.

## THE ONE THING TO DO NEXT

Run `calassist` yourself and exercise the revision loop. It has never been
driven by a human — an acceptance bug swallowed every "yes" until late in the
session, so the flow has only ever been verified by scripts.

When the chart opens, give it these corrections (all three were real misses
in the last run):

    add travel to the grocery store, make grocery 20 minutes with no gap
    before meal prep, and move the Discover call to Tuesday afternoon

Then confirm with "yes" / "perfect" / anything affirmative, and "yes" again
at the write prompt. Watch whether it actually applies all three.

## Known issues, unfixed

1. AGENT IGNORES SOME EXPLICIT INSTRUCTIONS. Last run it booked 30 minutes of
   grocery when told 20, and put the Discover call Wednesday morning when told
   Tuesday afternoon. Prompt-tuning problem, not a code bug.
2. IT LEFT A 30-MINUTE HOLE on Monday (grocery 4:00, meal prep 4:30) despite
   the no-idle-gaps rule. Worth watching whether it repeats.
3. NO TRAVEL BLOCK to the grocery store even though the trip was described.
4. RE-PLANNING AN ALREADY-PLANNED WEEK is untested. The agent now sees its own
   previous blocks tagged as replaceable, but nothing has exercised that path.

## Fixed late in the session (all verified)

- "yes" accepts a proposal. It used to require a bare Enter; anything typed
  went back to the agent as an edit request, so the calendar was never written.
- Preview no longer draws CalAssist's own past blocks under the new proposal.
- Chart: 12-hour times, proportional block heights, one element per event,
  no rule through a block, auto-sized labels, notes in a right-hand column.
- Live spinner naming the tool in progress.
- Travel blocks end exactly at event start; no travel home unless something
  follows.
- Empty input re-prompts instead of quitting.

## Where things live

    ~/Projects/calassist/            code (public repo)
    ~/.config/calassist/             credentials, mode 600, never committed
    ~/Documents/calassist-priorities.md   priorities + the Defaults section
