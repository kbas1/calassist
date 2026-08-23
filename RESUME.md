# Where CalAssist stands — paused 2026-08-23

## Run it

    cd ~/Projects/calassist
    source .venv/bin/activate
    python -m src.main plan            # converse, preview, revise; writes nothing
    python -m src.main plan --write    # same, then asks [y/N] before creating

## Done (13 commits, 54 tests passing)

- Security: credentials in ~/.config/calassist (mode 600), pre-commit hook
  (tested blocking), gitleaks CI, SECURITY.md
- Google OAuth, CALENDAR SCOPE ONLY (no Docs access, deliberately)
- Calendar reading; declined meetings count as free time
- Free-slot arithmetic: work hours blocked by config, 15-min buffers, overflow
- Priorities read from ~/Documents/calassist-priorities.md
- Agent (claude-sonnet-5) with tools, commute estimation, categories
- Travel blocks for 20+ min commutes; category colours on Google Calendar
- HTML week preview; CLI with preview-by-default

## Unfinished

1. REVISION LOOP IS COMMITTED BUT UNVERIFIED. You can now answer the preview
   with feedback ("move the roadmap to Sunday") instead of only accepting.
   The end-to-end test was still running when we paused — run it and watch
   that a second, revised proposal actually appears.

2. Never done a real --write run. All writing so far was a colour probe that
   was cleaned up. The test calendar is currently empty of CalAssist events.

3. TASK 11 NOT RUN — the pre-publication audit. Do this BEFORE making the
   repo public: gitleaks over full history, verify no credential was ever
   committed, create the repo private first, then flip to public. Full
   checklist in docs/superpowers/plans/2026-08-23-calassist-v1.md.

4. Priorities file is still the blank template.

## Known quirks

- OAuth app is in Google "Testing" status, so the token expires every 7 days.
  Expected. auth.py handles it: prints one line, reopens the browser.
- Commute times are model estimates, not Maps API. Good enough for buffers.
- Agent asks about origin ambiguity (office vs home) rather than guessing —
  that is deliberate.
