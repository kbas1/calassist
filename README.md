# CalAssist

A local AI agent that plans my week. It reads my priorities file and Google
Calendar, asks about anything it can't work out, and proposes colour-coded time
blocks — which I approve before anything is written.

Built as a first agent project, so the code favours being readable over being
clever.

## What it does

```
$ python -m src.main plan --write

CalAssist: Your priorities list interview prep with no time estimate.
           How long do you need?
You: two sessions, two hours each

  Mon 08/24  17:30-18:00  [travel]   Travel to Pickleball
  Tue 08/25  19:15-21:15  [focus]    Interview Prep
  Thu 08/27  17:00-19:00  [focus]    Interview Prep
  Sun 08/30  09:00-12:00  [focus]    Roadmap Draft
  warning: Wednesday only had 105 free minutes after salsa — left open

  Visual preview:  file:///.../week-preview.html

Happy with this? Press Enter to accept, or say what to change.
You: move the roadmap to Saturday
```

- Reconciles a priorities file against what's already on the calendar
- Estimates commute from event locations and blocks travel time
- Asks rather than guessing when a duration is missing
- Colour-codes by category: focus / social / workout / errand / travel
- Renders a visual week preview before anything is created

## Design notes

**The agent has no write access.** It gets three read-only tools plus one that
records a proposal in memory. `src/writer.py` is the only module that touches a
calendar, and `src/main.py` calls it only after an explicit `y`.

**Code computes, the model judges.** `find_free_slots` does the interval
arithmetic — buffers, work hours, overlapping events — because LLMs are
unreliable at arithmetic. The model decides what belongs in the gaps it's
handed. That split is most of why this works.

**Work hours are blocked by configuration, not inferred.** The work calendar
lives on a different account and is invisible to this app. Without an explicit
`WEEKDAY_BLOCKED`, an empty-looking Tuesday 10am would get scheduled over.

**Calendar scope only.** Google's Docs API has no per-document scope, so
reading one priorities doc would have granted read access to *every* document
in the account. Priorities come from a local markdown file instead.

## Setup

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -r requirements.txt
mkdir -p ~/.config/calassist && chmod 700 ~/.config/calassist
cp .env.example ~/.config/calassist/env && chmod 600 ~/.config/calassist/env
git config core.hooksPath .githooks        # secret-blocking pre-commit hook
```

Google OAuth setup is in `docs/superpowers/plans/2026-08-23-calassist-v1.md`,
Task 2. Put the downloaded client file at
`~/.config/calassist/credentials.json`, then:

```bash
python -m src.auth      # opens a browser once
```

## Usage

```bash
python -m src.main plan            # converse, preview, revise — writes nothing
python -m src.main plan --write    # same, then asks before creating events
```

## Priorities file format

```markdown
## Week of 8.24

### Priorities
1. Interview prep - 4h
2. Roadmap draft - 3h

### Already scheduled
- Dentist - Tue 2pm

### To-dos
- Submit expenses (by Fri)
```

Time estimates drive scheduling. Numbered order decides what gets cut when the
week doesn't fit. Anything missing, CalAssist asks about.

## Security

No credentials live in this repository. They sit in `~/.config/calassist/`
(mode 600), outside the working tree, so git cannot see them. See
[SECURITY.md](SECURITY.md) for the full posture and the revoke-first runbook.

## Tests

```bash
python -m pytest -q      # 54 tests
```

## Licence

MIT
