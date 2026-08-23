# CalAssist — Design Spec

**Date:** 2026-08-23
**Status:** Approved, not yet implemented

## Context

Planning a week means reconciling two things that live in different places:
intent (a weekly priorities doc, a task list) and commitments (a calendar).
Doing it by hand means holding both in your head and guessing at what fits.

CalAssist is a local AI agent that reads both, asks the questions needed to
close the gaps, and proposes a week you approve in one step.

This is a first AI-agent project. Where a choice trades learning against
convenience, it favors learning — but never at the cost of safety around real
calendar data.

## The core constraint that shapes everything

**CalAssist connects to a personal Google account. Work commitments live on a
separate work calendar it cannot see.**

So weekday 8:30am–5:30pm is unavailable *by configuration*, not because any
event appears there. Without this rule CalAssist would see an empty Tuesday
10am and propose deep work during office hours.

The practical consequence: **CalAssist plans evenings and weekends, not
workdays** — roughly 20 bookable hours a week, not 40. That makes "what didn't
fit" the more valuable half of the output.

## Availability model

```
Blocked by config (work, invisible to CalAssist)
  Mon-Fri  8:30am - 5:00pm

Preferred bookable
  Mon-Fri  5:00pm - 9:00pm
  Sat-Sun  9:00am - 9:00pm

Overflow — used only when the week doesn't fit, always with a warning
  Mon-Fri  7:00am - 8:30am
  Any day  9:00pm - 10:00pm

Buffer: 15 minutes between a proposed block and any adjacent event.
```

**Decided: 5:00pm is bookable by default.** You are usually home by 3, and
occasionally as late as 5:30. If a first-evening block ever turns out to be
unusable on a late day, change `WEEKDAY_BLOCKED` to end at `17:30` — a one-line
edit, not a redesign.

## Architecture

```
$ calassist plan
      |
      +-- 1. auth.py       token.json exists ? use it : open browser
      |
      +-- 2. AGENT CONVERSATION  (claude-sonnet-5, SDK tool runner)
      |         tools -- ALL READ-ONLY:
      |           get_document(name)                  priorities / tasks
      |           get_calendar_events(from, to)       existing commitments
      |           find_free_slots(from, to, minutes)  computed gaps
      |
      |         ...asks questions, you answer, it proposes a week
      |
      +-- 3. preview.py    renders week-preview.html, prints file:// link
      |
      +-- 4. "Write these 4 events? [y/n]"
      |
      +-- 5. writer.py     ONLY runs after you type y
```

### The write boundary

The agent has **no write tool**. Creating events happens in `writer.py`, called
by `main.py` only after explicit approval. A misbehaving agent can propose
nonsense; it cannot put nonsense on the calendar.

### Division of labor: code computes, model judges

`find_free_slots` is a tool rather than something the model derives from raw
events. LLMs are unreliable at interval arithmetic and excellent at judgment.
Code finds the gaps; the model decides what belongs in them.

The inverse applies to matching doc items against calendar events (below) —
that is judgment, so the model does it rather than string comparison.

## Behavioral rules

### Deduplication — announced, never silent

Before proposing, CalAssist matches each doc item against existing calendar
events *semantically* ("Dentist" matches "Dentist appointment - Dr. Chen").
Matches are skipped and reported:

```
ALREADY ON YOUR CALENDAR - skipping
  Dentist         -> "Dentist appointment - Dr. Chen"  Tue 2pm
  Team offsite    -> "Q3 Offsite"                      Thu (all day)
```

Silent skipping is worse than double-booking — a mis-match must be visible.

### Other resolved cases

| Case | Rule |
|---|---|
| Missing duration on a priority | **Ask.** Never guess — wrong durations wreck the week |
| Partial completion (4h needed, 2h already booked) | Propose the remaining 2h, say so |
| Declined meetings | Treated as **free** |
| Tentative meetings | Treated as **busy** |
| Recurring events | Always fixed — never proposed, always busy |
| All-day events | **Ask each time** whether the day is usable |
| Old week sections in the doc | Read only the current week; mention unfinished prior items once |
| Conflict it cannot fix | Flag in `warnings` — CalAssist creates events, never moves or deletes |

## Priorities doc format

A convention between you and the agent, not enforced by code — so it can evolve
without touching Python.

```markdown
## Week of 8.24

### Priorities
1. NVIDIA interview prep - 4h
2. Q4 roadmap draft - 3h
3. Design review prep - 90m

### Already scheduled
- Team offsite - Thu, all day
- Dentist - Tue 2pm

### To-dos
- Submit expenses (by Fri)
- Reply to recruiter emails
```

Three things carry weight: **time estimates** drive scheduling, **numbered
priorities** define what gets cut when the week doesn't fit, and **"Already
scheduled"** prevents double-booking. Everything else is free-form.

Keep the `## Week of X` heading style consistent across weeks.

## Agent output contract

Structured output, so `main.py` receives a validated object rather than prose:

```json
{
  "blocks": [
    { "title": "Interview prep", "day": "2026-08-25",
      "start": "17:00", "end": "19:00",
      "reason": "first clear evening, 2 days before the interview" }
  ],
  "skipped_already_scheduled": [
    { "item": "Dentist", "matched": "Dentist appointment - Dr. Chen, Tue 2pm" }
  ],
  "not_scheduled": [
    { "item": "Design review prep", "why": "no 90-min slot left after priorities 1-2" }
  ],
  "warnings": [
    "Used Fri 7-8:30am to fit everything - your only early-morning block this week"
  ]
}
```

These four fields map directly onto the HTML preview.

## Files

```
~/Projects/calassist/
  .gitignore          written first, before any secret exists
  .env.example        committed; real .env is not
  requirements.txt
  README.md
  CLAUDE.md
  config.py           doc IDs, calendar ID, availability windows
  src/
    auth.py           Google OAuth              ~15 lines
    docs_read.py      Google Doc -> text        ~40 lines
    calendar_read.py  events + free slots       ~80 lines
    tools.py          @beta_tool wrappers       ~40 lines
    agent.py          tool-runner conversation  ~80 lines
    preview.py        HTML week grid            ~60 lines
    writer.py         create events             ~30 lines
    main.py           CLI entry                 ~50 lines
  outputs/
    week-preview.html
```

Flat `src/` matches the existing `job-tracker` layout.

## Security

- `token.json` is a password equivalent. Gitignored before it can exist.
- Scopes are minimal: `calendar` (write needed) and `documents.readonly`.
  A compromise cannot reach Gmail, Drive files, or contacts.
- Everything runs locally. Network calls go only to Google and Anthropic.
- Revoke anytime: myaccount.google.com -> Security -> Third-party apps.

**Known gotcha:** while the OAuth app is in "Testing" status, Google expires
refresh tokens after 7 days — maximally annoying for a weekly tool. Publish to
"In production" and click past the unverified-app warning. Documented in the
README so it doesn't ambush you at week two.

## Build phases

| Phase | Goal | Done when |
|---|---|---|
| 1 | Google OAuth only | `python src/auth.py` prints your next 10 events |
| 2 | Read docs, compute free slots | prints priorities doc + this week's real gaps |
| 3 | The agent | converses, asks about durations, proposes a week as text |
| 4 | Preview | color-coded HTML grid with a key, opened from a printed link |
| 5 | Writing | events land on a **test calendar**, gated behind `[y/n]` |

Phase 1 is first because OAuth is the most frustrating part and has nothing to
do with AI. Everything after it is momentum.

Phase 5 writes to a separate "CalAssist Test" calendar. Flip one line in
`config.py` when you trust it.

## Verification

- Phases 1-2 are plain functions — `pytest` against a recorded calendar fixture.
- Phase 3 has no meaningful unit test for "did it propose a sensible week." The
  safety net is the test calendar plus `--dry-run`, not coverage.
- End-to-end: run `calassist plan --dry-run` against a real week; confirm the
  proposal respects work hours, buffers, and dedupe. Then drop `--dry-run` and
  confirm events appear on the test calendar only.

## Cost

Model: `claude-sonnet-5`. About $0.11 per session, roughly $6/year at weekly
use. Google APIs and all authentication are free.

## Explicitly out of scope for v1

Moving or deleting existing events; multi-week planning; a web UI; work-calendar
integration; any hosted deployment.
