# CalAssist v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local terminal agent that reads a Google Doc of weekly priorities plus your Google Calendar, asks the questions needed to close gaps, and writes an approved set of time blocks back to your calendar.

**Architecture:** Python CLI. The Anthropic SDK's tool runner drives an agent loop with three read-only tools plus a `submit_proposal` tool it calls when ready. The agent has no write capability — `writer.py` creates events, and only after an explicit `[y/n]`. Deterministic work (finding calendar gaps) lives in Python; judgment (what belongs in a gap, whether a doc item matches an existing event) lives in the model.

**Tech Stack:** Python 3.12 (via `uv`), `anthropic` SDK with `claude-sonnet-5`, `google-api-python-client` + `google-auth-oauthlib`, `pytest`, stdlib `zoneinfo`.

**One deliberate deviation from the spec:** the spec described a `--dry-run`
flag. This plan inverts it — preview is the default and `--write` opts in.
Same behavior, but the safe path is the one you get when you forget a flag.

## Global Constraints

- Model is `claude-sonnet-5` everywhere. Never a date-suffixed variant.
- **No secret ever lives inside the repository directory.** Credentials live in `~/.config/calassist/` (mode 600). This repo is intended to be public; gitignore is a backstop, not the primary defense.
- Four independent layers must all pass before a secret could leak: files outside the repo, `.gitignore`, a pre-commit hook, and CI secret scanning.
- OAuth scopes are exactly: `https://www.googleapis.com/auth/calendar` and `https://www.googleapis.com/auth/documents.readonly`. Nothing broader.
- The agent gets **no** calendar-write tool. Writes happen only in `writer.py`.
- Work hours are blocked by config (`WEEKDAY_BLOCKED`), never inferred from events — the work calendar is invisible to this app.
- All datetimes are timezone-aware, in `config.TIMEZONE`. Never naive datetimes.
- Until Task 10 is verified, `CALASSIST_CALENDAR_ID` points at a test calendar, not `primary`.

---

### Task 0: Security hardening (do this before anything else)

This repository is intended to be **public**. Automated scrapers find committed
credentials within minutes of a push, and a leaked Google refresh token grants
read/write access to a real calendar. Four independent layers, so no single
mistake is sufficient to leak.

**Files:**
- Create: `.githooks/pre-commit`, `.github/workflows/secret-scan.yml`, `SECURITY.md`
- Modify: `.gitignore`
- Test: `tests/test_no_secrets_in_repo.py`

**Interfaces:**
- Consumes: nothing
- Produces: `~/.config/calassist/` (mode 700) as the credential home; a pre-commit hook that blocks credential commits

- [ ] **Step 1: Bootstrap the environment and the credential directory**

Task 0 runs tests, so the venv comes first:

```bash
cd ~/Projects/calassist
git init                       # the hook in Step 4 needs a repo to configure
mkdir -p tests && touch tests/__init__.py
uv venv --python 3.12
source .venv/bin/activate
uv pip install pytest
```

Then the credential directory — **outside the repo**:

```bash
mkdir -p ~/.config/calassist
chmod 700 ~/.config/calassist
```

**This is the primary defense.** `.gitignore` protects files that live inside
the repo; moving them outside means git cannot see them at all. `git add -A`,
`git add -f`, a mistyped pattern, a future `.gitignore` edit — none of it can
reach a file that isn't in the working tree.

- [ ] **Step 2: Replace .gitignore with the hardened version**

```
# ============================================================
# SECRETS — these should never exist inside this repo at all.
# Real credentials live in ~/.config/calassist/ (see SECURITY.md).
# These patterns are a BACKSTOP, not the primary defense.
# ============================================================
token.json
credentials.json
client_secret*.json
*.credentials.json
.env
.env.*
!.env.example
*.pem
*.key
*.p12
service-account*.json

# Python
__pycache__/
*.pyc
.venv/
venv/

# Generated output
outputs/*
!outputs/.gitkeep

# macOS
.DS_Store
```

- [ ] **Step 3: Write the pre-commit hook**

Create `.githooks/pre-commit`:

```bash
#!/usr/bin/env bash
# Refuse to commit anything that looks like a credential.
# Installed via: git config core.hooksPath .githooks
set -euo pipefail

FAIL=0

# --- Layer 1: forbidden filenames (catches even `git add -f`) ---
FORBIDDEN='(^|/)(token\.json|credentials\.json|client_secret.*\.json|service-account.*\.json|\.env)$'
if git diff --cached --name-only | grep -Eq "$FORBIDDEN"; then
  echo "BLOCKED - attempt to commit a credential file:"
  git diff --cached --name-only | grep -E "$FORBIDDEN" | sed 's/^/    /'
  FAIL=1
fi

# --- Layer 2: secret-shaped content in any staged file ---
declare -a PATTERNS=(
  'sk-ant-[A-Za-z0-9_-]{20,}'
  'ya29\.[A-Za-z0-9_-]{20,}'
  '"refresh_token"[[:space:]]*:[[:space:]]*"[^"]{20,}'
  '"client_secret"[[:space:]]*:[[:space:]]*"[^"]{10,}'
  '"private_key"[[:space:]]*:'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
  'AIza[0-9A-Za-z_-]{35}'
)
for pat in "${PATTERNS[@]}"; do
  if git diff --cached -U0 | grep -Eq "^\+.*${pat}"; then
    echo "BLOCKED - staged content matches a secret pattern:"
    echo "    ${pat}"
    FAIL=1
  fi
done

if [ "$FAIL" -ne 0 ]; then
  echo ""
  echo "Commit refused. Nothing was committed."
  echo "Inspect what is staged with:  git diff --cached"
  echo "This hook exists because this repo is public. Do not bypass it."
  exit 1
fi
```

- [ ] **Step 4: Install and verify the hook actually blocks**

```bash
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks

# Prove it works — this MUST be refused:
echo 'ANTHROPIC_API_KEY=sk-ant-api03-FAKEFAKEFAKEFAKEFAKEFAKE1234567890' > /tmp/leak.txt
cp /tmp/leak.txt ./leaktest.txt
git add -f leaktest.txt
git commit -m "should be blocked"
```

Expected: `BLOCKED - staged content matches a secret pattern` and **no commit
is created**. If it commits, the hook is not installed — stop and fix it.

```bash
git reset HEAD leaktest.txt && rm leaktest.txt /tmp/leak.txt
```

- [ ] **Step 5: Add CI secret scanning**

Create `.github/workflows/secret-scan.yml`:

```yaml
name: secret-scan

on:
  push:
  pull_request:

jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0     # full history, not just the tip
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

This scans **entire history** on every push, so a secret committed and later
deleted still fails the build — deleting a file does not remove it from git
history.

- [ ] **Step 6: Write the repo-hygiene test**

Create `tests/test_no_secrets_in_repo.py`:

```python
"""Guard rails that fail loudly if the security posture regresses."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORBIDDEN_NAMES = ["token.json", "credentials.json", ".env"]


def test_no_credential_files_in_working_tree():
    """Credentials belong in ~/.config/calassist/, never in the repo."""
    for name in FORBIDDEN_NAMES:
        assert not (REPO / name).exists(), (
            f"{name} exists inside the repo. Move it to ~/.config/calassist/ "
            f"— this repo is public."
        )


def test_no_credential_files_tracked_by_git():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True
    ).stdout.split()
    for path in tracked:
        assert Path(path).name not in FORBIDDEN_NAMES, f"{path} is tracked by git"


def test_pre_commit_hook_is_installed():
    result = subprocess.run(
        ["git", "config", "core.hooksPath"], cwd=REPO, capture_output=True, text=True
    )
    assert result.stdout.strip() == ".githooks", (
        "Pre-commit hook not installed. Run: git config core.hooksPath .githooks"
    )


def test_gitignore_covers_the_credential_names():
    ignored = (REPO / ".gitignore").read_text()
    for name in ["token.json", "credentials.json", ".env"]:
        assert name in ignored
```

- [ ] **Step 7: Run the tests**

```bash
python -m pytest tests/test_no_secrets_in_repo.py -v
```

Expected: 4 passed.

- [ ] **Step 8: Write SECURITY.md**

```markdown
# Security

This repository is public. It contains **no credentials** by design.

## Where secrets actually live

    ~/.config/calassist/credentials.json    Google OAuth client
    ~/.config/calassist/token.json          your calendar access token
    ~/.config/calassist/env                 API keys and IDs

All mode 600, in a mode 700 directory, outside the repository. Git cannot
see them.

## Four independent layers

1. **Location** — secrets are outside the working tree, so `git add -A`
   cannot reach them.
2. **`.gitignore`** — backstop if a file is ever copied in by mistake.
3. **Pre-commit hook** (`.githooks/pre-commit`) — refuses commits containing
   credential filenames or secret-shaped content. Install with
   `git config core.hooksPath .githooks`.
4. **CI scanning** — gitleaks runs over full history on every push.

Plus GitHub's own secret scanning and push protection, enabled in repo
settings.

## Scopes are minimal

    https://www.googleapis.com/auth/calendar             read + write events
    https://www.googleapis.com/auth/documents.readonly   read docs only

A compromised token cannot reach Gmail, Drive files, or contacts. Docs access
is read-only — CalAssist has no reason to edit your documents.

## If a token leaks anyway

Do these in order, immediately:

1. **Revoke Google access.** myaccount.google.com > Security >
   Your connections to third-party apps > CalAssist > Remove access.
   This invalidates the token instantly, before anything else.
2. **Revoke the Anthropic key.** console.anthropic.com > API keys > delete.
3. **Delete the OAuth client** in Google Cloud console > Credentials, and
   create a new one.
4. Only then worry about scrubbing git history. **Rotation comes first —
   a token in history is harmless once revoked, and a token you scrubbed
   but did not revoke is still live.**

## Before making this repo public

Run the checklist in the implementation plan, Task 11.
```

- [ ] **Step 9: Commit**

```bash
git add .gitignore .githooks SECURITY.md .github tests/test_no_secrets_in_repo.py
git commit -m "security: credentials outside repo, pre-commit hook, CI scanning"
```

Expected: the hook runs on this very commit and passes.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`, `.env.example`, `config.py`, `src/__init__.py`, `tests/__init__.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `config.TIMEZONE` (`ZoneInfo`), `config.WEEKDAY_BLOCKED` (`tuple[time, time]`), `config.WEEKDAY_BOOKABLE` / `WEEKEND_BOOKABLE` / `WEEKDAY_OVERFLOW` / `EVENING_OVERFLOW` (`list[tuple[time, time]]`), `config.BUFFER_MINUTES` (`int`), `config.TARGET_CALENDAR_ID` (`str`), `config.PRIORITIES_DOC_ID` / `TASKS_DOC_ID` (`str | None`), `config.MODEL` (`str`)

- [ ] **Step 1: Confirm the environment from Task 0 is active**

```bash
cd ~/Projects/calassist && source .venv/bin/activate && python --version
```

Expected: `Python 3.12.x`. (The venv was created in Task 0.)

- [ ] **Step 2: Write requirements.txt**

```
anthropic>=0.69.0
google-api-python-client>=2.140.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 3: Install, and pin the pytest import path**

```bash
uv pip install -r requirements.txt
```

Expected: ends with `Installed N packages`.

Create `pytest.ini` so tests can `import config` and `import src.*`
regardless of where pytest is invoked from:

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 4: Write .env.example**

```
# TEMPLATE ONLY - contains no real values.
# Copy to ~/.config/calassist/env (NOT into this repo) and fill in:
#     cp .env.example ~/.config/calassist/env
#     chmod 600 ~/.config/calassist/env
ANTHROPIC_API_KEY=PUT-YOUR-KEY-HERE

# Google Doc IDs — the long string in the doc's URL:
# docs.google.com/document/d/THIS_PART/edit
PRIORITIES_DOC_ID=
TASKS_DOC_ID=

# Calendar to WRITE to. Keep this as a test calendar until you trust it.
# Find it: Google Calendar > calendar settings > Integrate calendar > Calendar ID
CALASSIST_CALENDAR_ID=
```

- [ ] **Step 5: Write config.py**

```python
"""Configuration for CalAssist.

Work hours are blocked here BY RULE, not by reading events. CalAssist
connects to a personal Google account; work commitments live on a separate
calendar it cannot see. Without WEEKDAY_BLOCKED it would treat an empty
Tuesday 10am as free and propose deep work during office hours.
"""
import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Credentials live OUTSIDE the repo. This project is public; a secret that is
# not in the working tree cannot be committed by any accident.
CONFIG_DIR = Path(
    os.getenv("CALASSIST_CONFIG_DIR", Path.home() / ".config" / "calassist")
)
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
ENV_FILE = CONFIG_DIR / "env"

load_dotenv(ENV_FILE)

TIMEZONE = ZoneInfo("America/New_York")
MODEL = "claude-sonnet-5"

# Commute + office. Invisible to this app, so blocked by rule.
WEEKDAY_BLOCKED = (time(8, 30), time(17, 0))

# Preferred bookable windows.
WEEKDAY_BOOKABLE = [(time(17, 0), time(21, 0))]
WEEKEND_BOOKABLE = [(time(9, 0), time(21, 0))]

# Used ONLY when the week doesn't fit. Always produces a warning.
WEEKDAY_OVERFLOW = [(time(7, 0), time(8, 30))]
EVENING_OVERFLOW = [(time(21, 0), time(22, 0))]

# Minimum gap between a proposed block and any adjacent event.
BUFFER_MINUTES = 15

TARGET_CALENDAR_ID = os.getenv("CALASSIST_CALENDAR_ID", "primary")
PRIORITIES_DOC_ID = os.getenv("PRIORITIES_DOC_ID")
TASKS_DOC_ID = os.getenv("TASKS_DOC_ID")
```

- [ ] **Step 6: Write the failing test**

Create `tests/test_config.py`:

```python
from datetime import time

import config


def test_weekday_blocked_ends_where_bookable_begins():
    """Work must end exactly when evening booking starts — no gap, no overlap."""
    _, blocked_end = config.WEEKDAY_BLOCKED
    first_bookable_start, _ = config.WEEKDAY_BOOKABLE[0]
    assert blocked_end == first_bookable_start


def test_overflow_windows_do_not_intrude_on_work():
    """Early-morning overflow must finish before the commute starts."""
    blocked_start, _ = config.WEEKDAY_BLOCKED
    for _, overflow_end in config.WEEKDAY_OVERFLOW:
        assert overflow_end <= blocked_start


def test_buffer_is_positive():
    assert config.BUFFER_MINUTES > 0
```

- [ ] **Step 7: Run the tests**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 3 passed. (These are guard-rail tests — they fail loudly if someone later edits `config.py` into an inconsistent state, which is exactly the bug the spec's self-review caught.)

- [ ] **Step 8: Commit**

```bash
git add .gitignore requirements.txt .env.example config.py src/ tests/ docs/ outputs/.gitkeep
git commit -m "feat: project scaffolding and availability config"
```

---

### Task 2: Google Cloud setup and OAuth

**Files:**
- Create: `src/auth.py`
- Test: manual smoke test (OAuth cannot be meaningfully unit tested)

**Interfaces:**
- Consumes: `config` (nothing yet)
- Produces: `auth.get_credentials() -> google.oauth2.credentials.Credentials`, `auth.SCOPES: list[str]`

- [ ] **Step 1: Create the Google Cloud project (manual, ~10 min)**

In a browser, logged into **the Google account CalAssist should manage** (not necessarily your Claude account):

1. console.cloud.google.com → project dropdown → **New Project** → name it `calassist` → Create
2. **APIs & Services → Library** → search "Google Calendar API" → **Enable**
3. Same Library → search "Google Docs API" → **Enable**
4. **APIs & Services → OAuth consent screen** → choose **External** → fill app name `CalAssist`, your email for both support fields → Save
5. On the consent screen summary, click **Publish app** → confirm. *This matters:* apps left in "Testing" have their refresh tokens expire after **7 days**, which for a weekly tool means re-authorizing almost every session. Published apps show a one-time "unverified app" warning you click past.
6. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → Application type **Desktop app** → Create → **Download JSON**
7. Move the downloaded file **outside the repo**, into the credential dir:

```bash
mv ~/Downloads/client_secret_*.json ~/.config/calassist/credentials.json
chmod 600 ~/.config/calassist/credentials.json
```

Note it does **not** go in the project folder. This repo is public.

- [ ] **Step 2: Verify nothing secret is inside the repo**

```bash
cd ~/Projects/calassist
ls credentials.json token.json .env 2>&1     # expect: No such file (all three)
ls -l ~/.config/calassist/                   # expect: credentials.json, mode -rw-------
python -m pytest tests/test_no_secrets_in_repo.py -v
```

Expected: the three files do **not** exist in the repo, `credentials.json` is
mode `600` in `~/.config/calassist/`, and all 4 hygiene tests pass.

- [ ] **Step 3: Write src/auth.py**

```python
"""Google OAuth for CalAssist.

Two files do the work, and BOTH live in ~/.config/calassist/, never in this
repository:
  credentials.json  the app's ID badge (downloaded from Cloud console)
  token.json        YOUR access key, created on first run - password equivalent

This repo is public. Keeping these outside the working tree means git cannot
see them at all - stronger than relying on .gitignore.

Revoke anytime: myaccount.google.com > Security > Third-party apps.
"""
import os
import stat

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import config

# Narrowest scopes that do the job. Calendar needs write (we create events);
# Docs is read-only — CalAssist has no reason to edit your documents.
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents.readonly",
]

CREDENTIALS_FILE = config.CREDENTIALS_FILE
TOKEN_FILE = config.TOKEN_FILE


def _write_private(path, content: str) -> None:
    """Write a secret with owner-only permissions (mode 600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(stat.S_IRWXU)                  # 700
    with open(path, "w") as f:
        f.write(content)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)          # 600


def get_credentials() -> Credentials:
    """Return valid credentials, refreshing or prompting in a browser if needed."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())          # silent renewal
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"{CREDENTIALS_FILE} not found. Download it from the Google "
                    "Cloud console (APIs & Services > Credentials > OAuth client "
                    "ID > Desktop app) and move it there - NOT into this repo."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)   # opens browser
        _write_private(TOKEN_FILE, creds.to_json())

    return creds
```

- [ ] **Step 4: Write the smoke test**

Append to `src/auth.py`:

```python
if __name__ == "__main__":
    from googleapiclient.discovery import build

    service = build("calendar", "v3", credentials=get_credentials())
    calendars = service.calendarList().list().execute().get("items", [])
    print(f"Authenticated. {len(calendars)} calendars visible:\n")
    for cal in calendars:
        primary = " (primary)" if cal.get("primary") else ""
        print(f"  {cal['summary']}{primary}")
        print(f"      id: {cal['id']}")
```

- [ ] **Step 5: Run it**

```bash
python -m src.auth
```

Expected: a browser opens → you pick the Google account → "unverified app" warning → **Advanced → Go to CalAssist (unsafe)** → Allow → terminal lists your calendars with their IDs. A `token.json` appears in the project root.

**This is the hardest part of the whole project and it is now done.**

- [ ] **Step 6: Create the test calendar**

In Google Calendar (same account): left sidebar → **Other calendars → +** → **Create new calendar** → name `CalAssist Test` → Create. Then Settings for that calendar → **Integrate calendar** → copy the **Calendar ID**.

```bash
cp .env.example ~/.config/calassist/env
chmod 600 ~/.config/calassist/env
$EDITOR ~/.config/calassist/env
```

Put that Calendar ID in as `CALASSIST_CALENDAR_ID`, and your Anthropic key as
`ANTHROPIC_API_KEY`. **The file goes in `~/.config/calassist/`, not the repo.**

- [ ] **Step 7: Verify the repo is still clean**

```bash
git status --short
```

Expected: only `src/auth.py`. No `token.json`, `credentials.json`, or `.env` —
they are not in the working tree at all.

```bash
python -m pytest tests/test_no_secrets_in_repo.py -v    # 4 passed
```

- [ ] **Step 8: Commit**

```bash
git add src/auth.py
git commit -m "feat: Google OAuth with calendar + docs read-only scopes"
```

---

### Task 3: Read calendar events

**Files:**
- Create: `src/calendar_read.py`
- Test: `tests/test_calendar_read.py`

**Interfaces:**
- Consumes: `auth.get_credentials()`, `config.TIMEZONE`
- Produces: `calendar_read.Event` (dataclass: `summary: str`, `start: datetime`, `end: datetime`, `all_day: bool`, `recurring: bool`, `response_status: str`), `calendar_read.fetch_events(start: datetime, end: datetime, calendar_id: str = "primary") -> list[Event]`, `calendar_read.is_busy(event: Event) -> bool`

- [ ] **Step 1: Write the failing test**

Create `tests/test_calendar_read.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from src.calendar_read import Event, is_busy

TZ = ZoneInfo("America/New_York")


def _event(**kwargs):
    defaults = dict(
        summary="Meeting",
        start=datetime(2026, 8, 25, 10, 0, tzinfo=TZ),
        end=datetime(2026, 8, 25, 11, 0, tzinfo=TZ),
        all_day=False,
        recurring=False,
        response_status="accepted",
    )
    defaults.update(kwargs)
    return Event(**defaults)


def test_accepted_meeting_is_busy():
    assert is_busy(_event(response_status="accepted")) is True


def test_declined_meeting_is_free():
    """You said no. That time is yours."""
    assert is_busy(_event(response_status="declined")) is False


def test_tentative_meeting_is_busy():
    """Might happen — don't double-book against it."""
    assert is_busy(_event(response_status="tentative")) is True


def test_event_with_no_response_status_is_busy():
    """Events you created yourself have no attendee status."""
    assert is_busy(_event(response_status="")) is True
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_calendar_read.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.calendar_read'`

- [ ] **Step 3: Write src/calendar_read.py**

```python
"""Read events from Google Calendar."""
from dataclasses import dataclass
from datetime import datetime

from googleapiclient.discovery import build

from src.auth import get_credentials

# Attendee response statuses that still consume your time.
BUSY_STATUSES = {"accepted", "tentative", "needsAction", ""}


@dataclass
class Event:
    summary: str
    start: datetime
    end: datetime
    all_day: bool
    recurring: bool
    response_status: str


def is_busy(event: Event) -> bool:
    """Does this event actually consume time?

    Declined meetings do not — that time is free even though the event
    is still on the calendar.
    """
    return event.response_status in BUSY_STATUSES


def _my_response(raw: dict) -> str:
    for attendee in raw.get("attendees", []):
        if attendee.get("self"):
            return attendee.get("responseStatus", "")
    return ""


def fetch_events(start: datetime, end: datetime, calendar_id: str = "primary") -> list[Event]:
    """Fetch events between two timezone-aware datetimes, expanding recurrences."""
    service = build("calendar", "v3", credentials=get_credentials())
    raw_events = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,       # expand recurring series into instances
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )

    events = []
    for raw in raw_events:
        all_day = "date" in raw["start"]
        if all_day:
            start_dt = datetime.fromisoformat(raw["start"]["date"])
            end_dt = datetime.fromisoformat(raw["end"]["date"])
        else:
            start_dt = datetime.fromisoformat(raw["start"]["dateTime"])
            end_dt = datetime.fromisoformat(raw["end"]["dateTime"])

        events.append(
            Event(
                summary=raw.get("summary", "(no title)"),
                start=start_dt,
                end=end_dt,
                all_day=all_day,
                recurring="recurringEventId" in raw,
                response_status=_my_response(raw),
            )
        )
    return events
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_calendar_read.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Smoke test against your real calendar**

```bash
python -c "
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from src.calendar_read import fetch_events, is_busy
tz = ZoneInfo('America/New_York')
now = datetime.now(tz)
for e in fetch_events(now, now + timedelta(days=7)):
    flag = 'busy' if is_busy(e) else 'FREE (declined)'
    print(f'{e.start:%a %m/%d %H:%M}  {e.summary[:40]:40} {flag}')
"
```

Expected: your actual next-7-days events, with any declined ones marked FREE.

- [ ] **Step 6: Commit**

```bash
git add src/calendar_read.py tests/test_calendar_read.py
git commit -m "feat: fetch calendar events, treat declined as free"
```

---

### Task 4: Compute free slots

This is the arithmetic half of the "code computes, model judges" split, and the most testable code in the project.

**Files:**
- Create: `src/availability.py`
- Test: `tests/test_availability.py`

**Interfaces:**
- Consumes: `config.*`, `calendar_read.Event`, `calendar_read.is_busy`
- Produces: `availability.Slot` (`NamedTuple`: `start: datetime`, `end: datetime`, `is_overflow: bool`), `availability.merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]`, `availability.bookable_windows(day: date, include_overflow: bool) -> list[tuple[datetime, datetime]]`, `availability.find_free_slots(events: list[Event], start_date: date, end_date: date, minimum_minutes: int, include_overflow: bool = False) -> list[Slot]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_availability.py`:

```python
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.availability import bookable_windows, find_free_slots, merge_intervals
from src.calendar_read import Event

TZ = ZoneInfo("America/New_York")
MONDAY = date(2026, 8, 24)
SATURDAY = date(2026, 8, 29)


def dt(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ)


def busy(d: date, start_h: int, end_h: int, **kw) -> Event:
    defaults = dict(
        summary="Thing", all_day=False, recurring=False, response_status="accepted"
    )
    defaults.update(kw)
    return Event(start=dt(d, start_h), end=dt(d, end_h), **defaults)


# --- merge_intervals -------------------------------------------------

def test_merge_leaves_disjoint_intervals_alone():
    a = (dt(MONDAY, 17), dt(MONDAY, 18))
    b = (dt(MONDAY, 19), dt(MONDAY, 20))
    assert merge_intervals([a, b]) == [a, b]


def test_merge_combines_overlapping_intervals():
    a = (dt(MONDAY, 17), dt(MONDAY, 19))
    b = (dt(MONDAY, 18), dt(MONDAY, 20))
    assert merge_intervals([a, b]) == [(dt(MONDAY, 17), dt(MONDAY, 20))]


def test_merge_combines_touching_intervals():
    a = (dt(MONDAY, 17), dt(MONDAY, 18))
    b = (dt(MONDAY, 18), dt(MONDAY, 19))
    assert merge_intervals([a, b]) == [(dt(MONDAY, 17), dt(MONDAY, 19))]


# --- bookable_windows ------------------------------------------------

def test_weekday_window_is_evening_only():
    assert bookable_windows(MONDAY, include_overflow=False) == [
        (dt(MONDAY, 17), dt(MONDAY, 21))
    ]


def test_weekend_window_is_all_day():
    assert bookable_windows(SATURDAY, include_overflow=False) == [
        (dt(SATURDAY, 9), dt(SATURDAY, 21))
    ]


def test_overflow_adds_early_morning_and_late_evening_on_weekdays():
    windows = bookable_windows(MONDAY, include_overflow=True)
    assert (dt(MONDAY, 7), dt(MONDAY, 8, 30)) in windows
    assert (dt(MONDAY, 21), dt(MONDAY, 22)) in windows


# --- find_free_slots -------------------------------------------------

def test_empty_calendar_gives_whole_evening():
    slots = find_free_slots([], MONDAY, MONDAY, minimum_minutes=60)
    assert slots == [(dt(MONDAY, 17), dt(MONDAY, 21), False)]


def test_work_hours_are_never_offered():
    """The whole point: 10am Monday is invisible to us but you're at the office."""
    slots = find_free_slots([], MONDAY, MONDAY, minimum_minutes=60)
    for start, _, _ in slots:
        assert start.hour >= 17


def test_event_splits_the_evening_and_applies_buffer():
    """A 6-7pm event should leave 5:00-5:45 and 7:15-9:00 (15 min buffers)."""
    slots = find_free_slots([busy(MONDAY, 18, 19)], MONDAY, MONDAY, minimum_minutes=30)
    assert slots == [
        (dt(MONDAY, 17), dt(MONDAY, 17, 45), False),
        (dt(MONDAY, 19, 15), dt(MONDAY, 21), False),
    ]


def test_slots_shorter_than_minimum_are_dropped():
    """Same event, but asking for 2 hours — only the later slot qualifies."""
    slots = find_free_slots([busy(MONDAY, 18, 19)], MONDAY, MONDAY, minimum_minutes=120)
    assert slots == [(dt(MONDAY, 19, 15), dt(MONDAY, 21), False)]


def test_declined_event_does_not_block_time():
    events = [busy(MONDAY, 18, 19, response_status="declined")]
    slots = find_free_slots(events, MONDAY, MONDAY, minimum_minutes=60)
    assert slots == [(dt(MONDAY, 17), dt(MONDAY, 21), False)]


def test_full_evening_leaves_nothing():
    slots = find_free_slots([busy(MONDAY, 17, 21)], MONDAY, MONDAY, minimum_minutes=30)
    assert slots == []


def test_overflow_slots_are_flagged():
    slots = find_free_slots(
        [busy(MONDAY, 17, 21)], MONDAY, MONDAY, minimum_minutes=60, include_overflow=True
    )
    assert all(slot.is_overflow for slot in slots)
    assert len(slots) > 0
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_availability.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.availability'`

- [ ] **Step 3: Write src/availability.py**

```python
"""Find bookable gaps.

Deterministic interval arithmetic. The model never does this — it is
unreliable at arithmetic and excellent at judgment, so code finds the gaps
and the model decides what belongs in them.
"""
from datetime import date, datetime, time, timedelta
from typing import NamedTuple

import config
from src.calendar_read import Event, is_busy


class Slot(NamedTuple):
    start: datetime
    end: datetime
    is_overflow: bool


def _at(day: date, t: time) -> datetime:
    return datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=config.TIMEZONE)


def merge_intervals(
    intervals: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """Collapse overlapping or touching intervals into the fewest possible."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:                       # overlaps or touches
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def bookable_windows(day: date, include_overflow: bool) -> list[tuple[datetime, datetime]]:
    """The windows we may schedule in on this day, before subtracting events."""
    is_weekend = day.weekday() >= 5
    base = config.WEEKEND_BOOKABLE if is_weekend else config.WEEKDAY_BOOKABLE
    windows = [(_at(day, s), _at(day, e)) for s, e in base]

    if include_overflow:
        extra = list(config.EVENING_OVERFLOW)
        if not is_weekend:
            extra += config.WEEKDAY_OVERFLOW
        windows += [(_at(day, s), _at(day, e)) for s, e in extra]

    return sorted(windows)


def find_free_slots(
    events: list[Event],
    start_date: date,
    end_date: date,
    minimum_minutes: int,
    include_overflow: bool = False,
) -> list[Slot]:
    """Bookable gaps of at least `minimum_minutes`, buffered away from events."""
    buffer = timedelta(minutes=config.BUFFER_MINUTES)
    minimum = timedelta(minutes=minimum_minutes)

    # Expand each busy event by the buffer on both sides, then merge.
    blocked = merge_intervals(
        [(e.start - buffer, e.end + buffer) for e in events if is_busy(e)]
    )

    slots: list[Slot] = []
    day = start_date
    while day <= end_date:
        preferred = set(bookable_windows(day, include_overflow=False))
        for window_start, window_end in bookable_windows(day, include_overflow):
            is_overflow = (window_start, window_end) not in preferred
            cursor = window_start
            for busy_start, busy_end in blocked:
                if busy_end <= cursor or busy_start >= window_end:
                    continue                        # no intersection
                if busy_start - cursor >= minimum:
                    slots.append(Slot(cursor, busy_start, is_overflow))
                cursor = max(cursor, busy_end)
            if window_end - cursor >= minimum:
                slots.append(Slot(cursor, window_end, is_overflow))
        day += timedelta(days=1)

    return sorted(slots)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_availability.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/availability.py tests/test_availability.py
git commit -m "feat: free-slot computation with buffers, overflow, work-hour blocking"
```

---

### Task 5: Read Google Docs

**Files:**
- Create: `src/docs_read.py`
- Test: `tests/test_docs_read.py`

**Interfaces:**
- Consumes: `auth.get_credentials()`
- Produces: `docs_read.fetch_document(doc_id: str) -> str`, `docs_read.extract_week_section(text: str, week_label: str) -> str | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_docs_read.py`:

```python
from src.docs_read import extract_week_section

DOC = """# Planning

## Week of 8.17
### Priorities
1. Old thing - 2h

## Week of 8.24
### Priorities
1. NVIDIA interview prep - 4h
2. Q4 roadmap draft - 3h

### Already scheduled
- Dentist - Tue 2pm

## Week of 8.31
### Priorities
1. Future thing - 1h
"""


def test_extracts_only_the_requested_week():
    section = extract_week_section(DOC, "8.24")
    assert "NVIDIA interview prep" in section
    assert "Old thing" not in section
    assert "Future thing" not in section


def test_includes_all_subsections_of_that_week():
    section = extract_week_section(DOC, "8.24")
    assert "Already scheduled" in section
    assert "Dentist" in section


def test_returns_none_when_week_absent():
    assert extract_week_section(DOC, "9.14") is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_docs_read.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.docs_read'`

- [ ] **Step 3: Write src/docs_read.py**

```python
"""Read Google Docs as plain text."""
import re

from googleapiclient.discovery import build

from src.auth import get_credentials


def fetch_document(doc_id: str) -> str:
    """Return the document's text content, flattened."""
    service = build("docs", "v1", credentials=get_credentials())
    doc = service.documents().get(documentId=doc_id).execute()

    lines = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        text = "".join(
            run.get("textRun", {}).get("content", "")
            for run in paragraph.get("elements", [])
        )
        lines.append(text.rstrip("\n"))
    return "\n".join(lines)


def extract_week_section(text: str, week_label: str) -> str | None:
    """Return just the '## Week of <label>' section.

    Old weeks accumulate in the doc; reading all of them would pull stale
    priorities into this week's plan.
    """
    pattern = rf"^##\s*Week of\s*{re.escape(week_label)}\s*$"
    lines = text.splitlines()

    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip(), re.IGNORECASE):
            start = i
            break
    if start is None:
        return None

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^##\s*Week of", lines[i].strip(), re.IGNORECASE):
            end = i
            break

    return "\n".join(lines[start:end]).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_docs_read.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Smoke test against your real doc**

```bash
python -c "
import config
from src.docs_read import fetch_document
print(fetch_document(config.PRIORITIES_DOC_ID)[:500])
"
```

Expected: the first 500 characters of your priorities doc.

- [ ] **Step 6: Commit**

```bash
git add src/docs_read.py tests/test_docs_read.py
git commit -m "feat: read Google Docs and extract a single week section"
```

---

### Task 6: Agent tools

**Files:**
- Create: `src/tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `config.*`, `calendar_read.fetch_events`, `availability.find_free_slots`, `docs_read.fetch_document` / `extract_week_section`
- Produces: `tools.Proposal` (dataclass), `tools.CAPTURED: dict`, `tools.get_document`, `tools.get_calendar_events`, `tools.find_free_slots_tool`, `tools.submit_proposal` (all `@beta_tool`-decorated), `tools.ALL_TOOLS: list`, `tools.validate_proposal(payload: dict) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools.py`:

```python
from src.tools import validate_proposal


def test_valid_proposal_has_no_errors():
    payload = {
        "blocks": [
            {"title": "Prep", "day": "2026-08-25", "start": "17:00",
             "end": "19:00", "reason": "first clear evening"}
        ],
        "skipped_already_scheduled": [],
        "not_scheduled": [],
        "warnings": [],
    }
    assert validate_proposal(payload) == []


def test_missing_top_level_key_is_reported():
    errors = validate_proposal({"blocks": []})
    assert any("skipped_already_scheduled" in e for e in errors)


def test_block_missing_a_field_is_reported():
    payload = {
        "blocks": [{"title": "Prep", "day": "2026-08-25", "start": "17:00"}],
        "skipped_already_scheduled": [],
        "not_scheduled": [],
        "warnings": [],
    }
    errors = validate_proposal(payload)
    assert any("end" in e for e in errors)


def test_bad_time_format_is_reported():
    payload = {
        "blocks": [{"title": "Prep", "day": "2026-08-25", "start": "5pm",
                    "end": "19:00", "reason": "x"}],
        "skipped_already_scheduled": [],
        "not_scheduled": [],
        "warnings": [],
    }
    errors = validate_proposal(payload)
    assert any("5pm" in e for e in errors)


def test_end_before_start_is_reported():
    payload = {
        "blocks": [{"title": "Prep", "day": "2026-08-25", "start": "19:00",
                    "end": "17:00", "reason": "x"}],
        "skipped_already_scheduled": [],
        "not_scheduled": [],
        "warnings": [],
    }
    errors = validate_proposal(payload)
    assert any("before" in e.lower() for e in errors)
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.tools'`

- [ ] **Step 3: Write src/tools.py**

```python
"""Tools the agent may call.

Every tool here is READ-ONLY except submit_proposal, which only records a
proposal in memory. Nothing in this file touches your calendar. Writing
happens in writer.py, after you approve.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from anthropic import beta_tool

import config
from src.availability import find_free_slots
from src.calendar_read import fetch_events, is_busy
from src.docs_read import extract_week_section, fetch_document

TIME_RE = re.compile(r"^\d{2}:\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_KEYS = ["blocks", "skipped_already_scheduled", "not_scheduled", "warnings"]
BLOCK_KEYS = ["title", "day", "start", "end", "reason"]


@dataclass
class Proposal:
    blocks: list = field(default_factory=list)
    skipped_already_scheduled: list = field(default_factory=list)
    not_scheduled: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# The agent's proposal lands here. main.py reads it after the run.
CAPTURED: dict = {"proposal": None}


def validate_proposal(payload: dict) -> list[str]:
    """Return human-readable problems with a proposal payload. Empty means valid."""
    errors = []
    for key in REQUIRED_KEYS:
        if key not in payload:
            errors.append(f"missing required key: {key}")
    if errors:
        return errors

    for i, block in enumerate(payload["blocks"]):
        for key in BLOCK_KEYS:
            if key not in block:
                errors.append(f"block {i} is missing '{key}'")
        if errors:
            continue
        if not DATE_RE.match(block["day"]):
            errors.append(f"block {i} day '{block['day']}' must be YYYY-MM-DD")
        for key in ("start", "end"):
            if not TIME_RE.match(block[key]):
                errors.append(f"block {i} {key} '{block[key]}' must be HH:MM 24-hour")
        if not errors and block["end"] <= block["start"]:
            errors.append(f"block {i} end {block['end']} is before start {block['start']}")

    return errors


@beta_tool
def get_document(name: str) -> str:
    """Read one of the user's planning documents.

    Args:
        name: Either "priorities" (the weekly priorities doc) or "tasks"
            (the running task list).
    """
    doc_id = {"priorities": config.PRIORITIES_DOC_ID, "tasks": config.TASKS_DOC_ID}.get(name)
    if not doc_id:
        return f"No document configured for '{name}'. Valid names: priorities, tasks."

    text = fetch_document(doc_id)
    if name == "priorities":
        monday = date.today() - timedelta(days=date.today().weekday())
        label = f"{monday.month}.{monday.day}"
        section = extract_week_section(text, label)
        if section:
            return section
        return (
            f"No '## Week of {label}' section found. Full document follows so you "
            f"can ask the user which section applies:\n\n{text}"
        )
    return text


@beta_tool
def get_calendar_events(start_date: str, end_date: str) -> str:
    """Read existing calendar commitments for a date range.

    Args:
        start_date: First day to read, as YYYY-MM-DD.
        end_date: Last day to read, as YYYY-MM-DD.
    """
    start = datetime.fromisoformat(start_date).replace(tzinfo=config.TIMEZONE)
    end = datetime.fromisoformat(end_date).replace(tzinfo=config.TIMEZONE) + timedelta(days=1)
    events = fetch_events(start, end)

    if not events:
        return "No events in that range."

    lines = []
    for e in events:
        tags = []
        if e.all_day:
            tags.append("ALL-DAY")
        if e.recurring:
            tags.append("recurring")
        if not is_busy(e):
            tags.append("DECLINED - time is free")
        suffix = f"  [{', '.join(tags)}]" if tags else ""
        when = f"{e.start:%Y-%m-%d %H:%M}-{e.end:%H:%M}"
        lines.append(f"{when}  {e.summary}{suffix}")
    return "\n".join(lines)


@beta_tool
def find_free_slots_tool(start_date: str, end_date: str, minimum_minutes: int,
                         include_overflow: bool = False) -> str:
    """Find bookable gaps, already accounting for work hours and buffers.

    Work hours (weekdays 8:30-17:00) are never returned — the user is at the
    office and that calendar is not visible to you.

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
    events = fetch_events(start, end)

    slots = find_free_slots(
        events, start.date(), end.date() - timedelta(days=1),
        minimum_minutes, include_overflow,
    )
    if not slots:
        return f"No free slots of at least {minimum_minutes} minutes."

    lines = []
    for s in slots:
        mins = int((s.end - s.start).total_seconds() // 60)
        tag = "  [OVERFLOW - warn the user]" if s.is_overflow else ""
        lines.append(f"{s.start:%Y-%m-%d %a %H:%M}-{s.end:%H:%M}  ({mins} min){tag}")
    return "\n".join(lines)


@beta_tool
def submit_proposal(proposal_json: str) -> str:
    """Submit the finished week. Call this exactly once, when ready.

    Args:
        proposal_json: A JSON object with exactly these four keys:
            blocks: list of {title, day (YYYY-MM-DD), start (HH:MM),
                end (HH:MM), reason}
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
    return "Proposal accepted. Stop here — do not call any more tools."


ALL_TOOLS = [get_document, get_calendar_events, find_free_slots_tool, submit_proposal]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tools.py tests/test_tools.py
git commit -m "feat: read-only agent tools plus validated proposal capture"
```

---

### Task 7: The agent

**Files:**
- Create: `src/agent.py`

**Interfaces:**
- Consumes: `config.MODEL`, `tools.ALL_TOOLS`, `tools.CAPTURED`, `tools.Proposal`
- Produces: `agent.SYSTEM_PROMPT: str`, `agent.run_conversation(first_message: str) -> Proposal | None`

- [ ] **Step 1: Write src/agent.py**

```python
"""The conversation loop.

The SDK's tool runner handles: call model -> run tool -> feed result back ->
repeat. We only supply the tools and the system prompt.
"""
from datetime import date, timedelta

import anthropic

import config
from src.tools import ALL_TOOLS, CAPTURED, Proposal

SYSTEM_PROMPT = """You are CalAssist, a weekly planning partner.

You help decide how to shape the coming week by reconciling the user's stated
priorities with what is already on their calendar, then proposing time blocks.

## Critical context about their schedule

They work in an office weekdays. That work calendar is NOT visible to you.
Weekdays 08:30-17:00 are unavailable even though you will see nothing there.
Never propose anything in those hours.

Their real bookable time is weekday evenings 17:00-21:00 and weekends
09:00-21:00 — roughly 20 hours a week, not 40. Use find_free_slots_tool rather
than reasoning about gaps yourself; it already applies these rules and a
15-minute buffer around existing events.

Overflow hours (weekday 07:00-08:30, and 21:00-22:00 any day) exist but are a
last resort. If you use one, say so in warnings.

## How to work

1. Read their priorities doc and task list.
2. Read their calendar for the target week.
3. Reconcile the two before proposing anything:
   - If a doc item is already on the calendar, do NOT propose it again. Match
     on meaning, not exact text: "Dentist" matches "Dentist appointment -
     Dr. Chen". Record every skip in skipped_already_scheduled so they can
     catch a bad match.
   - If something is partly done (4h needed, 2h already booked), propose only
     the remainder and say so.
4. ASK about anything you cannot determine. Specifically:
   - A priority with no time estimate: ask how long it needs. Never guess —
     a wrong duration ruins the week.
   - An all-day event: ask whether that day is usable at all.
   Ask these together in one message rather than one at a time.
5. Find slots and place blocks, highest-numbered priority first.
6. Call submit_proposal exactly once.

## Judgment

- Numbered priorities are ranked. When the week does not fit, drop from the
  bottom and explain what you dropped in not_scheduled.
- What did NOT fit is the most useful thing you tell them. Be specific about
  why.
- You can create events but cannot move or delete them. If an existing
  commitment is causing a problem, say so in warnings rather than working
  around it silently.
- Do not fill every available hour. Leaving space is a feature.

## Tone

Direct and brief. You are helping someone think, not writing a report.
"""


def run_conversation(first_message: str) -> Proposal | None:
    """Run the agent loop until it submits a proposal or asks a question.

    Returns the proposal, or None if the agent ended its turn asking something
    (in which case the caller collects an answer and calls again).
    """
    client = anthropic.Anthropic()
    CAPTURED["proposal"] = None

    messages = [{"role": "user", "content": first_message}]

    while True:
        runner = client.beta.messages.tool_runner(
            model=config.MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=messages,
        )

        last = None
        for message in runner:
            last = message
            messages.append({"role": "assistant", "content": message.content})
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                messages.append(tool_response)

            for block in message.content:
                if block.type == "text" and block.text.strip():
                    print(f"\nCalAssist: {block.text.strip()}\n")

        if CAPTURED["proposal"] is not None:
            return CAPTURED["proposal"]

        if last is None or last.stop_reason != "end_turn":
            return None

        # Agent asked something and stopped. Collect an answer and continue.
        reply = input("You: ").strip()
        if not reply or reply.lower() in {"quit", "exit"}:
            return None
        messages.append({"role": "user", "content": reply})


def opening_message(target_monday: date) -> str:
    sunday = target_monday + timedelta(days=6)
    return (
        f"Help me plan the week of {target_monday:%Y-%m-%d} through "
        f"{sunday:%Y-%m-%d}. Read my priorities and calendar first, ask me "
        f"anything you need, then propose the week."
    )
```

- [ ] **Step 2: Smoke test the conversation**

```bash
python -c "
from datetime import date, timedelta
from src.agent import run_conversation, opening_message
monday = date.today() - timedelta(days=date.today().weekday())
p = run_conversation(opening_message(monday))
print()
print('PROPOSAL:', p)
"
```

Expected: CalAssist reads your doc and calendar, asks about any missing durations, you answer, and it prints a `Proposal(...)` with blocks. **No events are created** — nothing here can write.

- [ ] **Step 3: Commit**

```bash
git add src/agent.py
git commit -m "feat: tool-runner conversation with planning system prompt"
```

---

### Task 8: HTML preview

**Files:**
- Create: `src/preview.py`
- Test: `tests/test_preview.py`

**Interfaces:**
- Consumes: `tools.Proposal`, `calendar_read.Event`
- Produces: `preview.render(proposal: Proposal, existing: list[Event], out_path: str = "outputs/week-preview.html") -> str` (returns absolute path)

- [ ] **Step 1: Write the failing test**

Create `tests/test_preview.py`:

```python
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from src.calendar_read import Event
from src.preview import render
from src.tools import Proposal

TZ = ZoneInfo("America/New_York")


def _proposal():
    return Proposal(
        blocks=[{"title": "Interview prep", "day": "2026-08-25",
                 "start": "17:00", "end": "19:00", "reason": "first clear evening"}],
        skipped_already_scheduled=[{"item": "Dentist", "matched": "Dentist - Dr. Chen"}],
        not_scheduled=[{"item": "Design review", "why": "no 90-min slot left"}],
        warnings=["Wed is wall to wall"],
    )


def _existing():
    return [Event(summary="Book club",
                  start=datetime(2026, 8, 26, 19, 0, tzinfo=TZ),
                  end=datetime(2026, 8, 26, 20, 30, tzinfo=TZ),
                  all_day=False, recurring=False, response_status="accepted")]


def test_render_writes_a_file(tmp_path):
    out = tmp_path / "week.html"
    path = render(_proposal(), _existing(), str(out))
    assert os.path.exists(path)


def test_html_contains_proposed_and_existing_and_all_sections(tmp_path):
    path = render(_proposal(), _existing(), str(tmp_path / "week.html"))
    html = open(path).read()
    assert "Interview prep" in html      # proposed block
    assert "Book club" in html           # existing commitment
    assert "Dentist" in html             # skipped section
    assert "Design review" in html       # not scheduled
    assert "Wed is wall to wall" in html # warnings
    assert "Already on your calendar" in html
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_preview.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.preview'`

- [ ] **Step 3: Write src/preview.py**

```python
"""Render the proposed week as a diff, not a snapshot.

The value is seeing what CalAssist wants to ADD against what is already
there — a mirror of your calendar would be pointless.
"""
import os
from datetime import datetime, timedelta

import config
from src.calendar_read import Event
from src.tools import Proposal

HOURS = list(range(7, 23))
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

CSS = """
:root { --bg:#fbfaf8; --fg:#1a1a1a; --line:#e0ddd8;
        --existing:#c9c4bb; --proposed:#3d7a5c; --work:#f0eeea; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#16161a; --fg:#e8e6e3; --line:#2e2e34;
  --existing:#4a4740; --proposed:#5fa882; --work:#1d1d22; } }
* { box-sizing: border-box; }
body { background:var(--bg); color:var(--fg); margin:0; padding:2rem;
       font:15px/1.5 ui-sans-serif, system-ui, -apple-system, sans-serif; }
h1 { font-size:1.4rem; margin:0 0 .25rem; }
.sub { color:#888; margin-bottom:1.5rem; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; min-width:640px; }
th,td { border:1px solid var(--line); padding:0; height:26px;
        text-align:center; font-size:12px; }
th { padding:6px 4px; font-weight:600; }
td.h { width:56px; color:#999; font-size:11px; padding-right:6px;
       text-align:right; border:none; }
.work { background:var(--work); }
.ex { background:var(--existing); }
.pr { background:var(--proposed); color:#fff; font-weight:600; }
.key { display:flex; gap:1.25rem; margin:1rem 0 2rem; flex-wrap:wrap;
       font-size:13px; align-items:center; }
.sw { display:inline-block; width:15px; height:15px; margin-right:6px;
      vertical-align:-3px; border:1px solid var(--line); }
section { margin-bottom:1.75rem; }
h2 { font-size:.8rem; text-transform:uppercase; letter-spacing:.07em;
     color:#888; margin:0 0 .6rem; }
li { margin-bottom:.4rem; }
.why { color:#888; }
"""


def _cells(proposal: Proposal, existing: list[Event], monday):
    """Map (day_index, hour) -> (css_class, label)."""
    grid = {}
    for e in existing:
        idx = (e.start.date() - monday).days
        if not 0 <= idx <= 6:
            continue
        for h in range(e.start.hour, max(e.start.hour + 1, e.end.hour)):
            grid[(idx, h)] = ("ex", e.summary)
    for b in proposal.blocks:
        day = datetime.fromisoformat(b["day"]).date()
        idx = (day - monday).days
        if not 0 <= idx <= 6:
            continue
        sh, eh = int(b["start"][:2]), int(b["end"][:2])
        for h in range(sh, max(sh + 1, eh)):
            grid[(idx, h)] = ("pr", b["title"])
    return grid


def render(proposal: Proposal, existing: list[Event],
           out_path: str = "outputs/week-preview.html") -> str:
    days = [datetime.fromisoformat(b["day"]).date() for b in proposal.blocks]
    days += [e.start.date() for e in existing]
    anchor = min(days) if days else datetime.now(config.TIMEZONE).date()
    monday = anchor - timedelta(days=anchor.weekday())

    grid = _cells(proposal, existing, monday)
    blocked_start, blocked_end = config.WEEKDAY_BLOCKED

    rows = []
    for h in HOURS:
        cells = [f'<td class="h">{h:02d}:00</td>']
        for d in range(7):
            key = grid.get((d, h))
            if key:
                cls, label = key
                cells.append(f'<td class="{cls}" title="{label}">{label[:11]}</td>')
            elif d < 5 and blocked_start.hour <= h < blocked_end.hour:
                cells.append('<td class="work" title="Work (not visible to CalAssist)"></td>')
            else:
                cells.append("<td></td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    headers = "".join(
        f"<th>{name}<br><span class='why'>{(monday + timedelta(days=i)):%m/%d}</span></th>"
        for i, name in enumerate(DAYS)
    )

    def section(title, items):
        if not items:
            return ""
        lis = "".join(items)
        return f"<section><h2>{title}</h2><ul>{lis}</ul></section>"

    skipped = section("Already on your calendar — skipped", [
        f"<li><strong>{s['item']}</strong> <span class='why'>&rarr; matched "
        f"&ldquo;{s['matched']}&rdquo;</span></li>"
        for s in proposal.skipped_already_scheduled])
    missed = section("Did not fit", [
        f"<li><strong>{n['item']}</strong> <span class='why'>&mdash; {n['why']}</span></li>"
        for n in proposal.not_scheduled])
    warns = section("Watch out", [f"<li>{w}</li>" for w in proposal.warnings])

    total = sum(
        (int(b["end"][:2]) * 60 + int(b["end"][3:]))
        - (int(b["start"][:2]) * 60 + int(b["start"][3:]))
        for b in proposal.blocks
    )

    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Week of {monday:%b %-d}</title><style>{CSS}</style></head><body>
<h1>Week of {monday:%B %-d}</h1>
<p class="sub">{len(proposal.blocks)} proposed blocks &middot;
   {total // 60}h {total % 60}m total</p>
<div class="key">
  <span><i class="sw pr"></i>CalAssist proposes</span>
  <span><i class="sw ex"></i>Already on your calendar</span>
  <span><i class="sw work"></i>Work (not visible to CalAssist)</span>
</div>
<div class="scroll"><table>
<tr><th></th>{headers}</tr>
{''.join(rows)}
</table></div>
{skipped}{missed}{warns}
</body></html>"""

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    return os.path.abspath(out_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_preview.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Look at it**

```bash
python -c "
from datetime import datetime
from zoneinfo import ZoneInfo
from src.calendar_read import Event
from src.preview import render
from src.tools import Proposal
tz = ZoneInfo('America/New_York')
p = Proposal(
  blocks=[{'title':'Interview prep','day':'2026-08-25','start':'17:00','end':'19:00','reason':'x'},
          {'title':'Roadmap','day':'2026-08-27','start':'17:30','end':'19:00','reason':'y'}],
  skipped_already_scheduled=[{'item':'Dentist','matched':'Dentist - Dr. Chen, Tue 2pm'}],
  not_scheduled=[{'item':'Design review prep','why':'no 90-min slot left'}],
  warnings=['Used Fri 07:00-08:30 to fit everything'])
e = [Event(summary='Book club', start=datetime(2026,8,26,19,0,tzinfo=tz),
           end=datetime(2026,8,26,20,30,tzinfo=tz), all_day=False,
           recurring=False, response_status='accepted')]
print(render(p, e))
" && open outputs/week-preview.html
```

Expected: a browser tab with a color-coded week grid, a key, and the three text sections. Check it in both light and dark mode.

- [ ] **Step 6: Commit**

```bash
git add src/preview.py tests/test_preview.py
git commit -m "feat: HTML week preview as a diff with color key"
```

---

### Task 9: Write events

**Files:**
- Create: `src/writer.py`
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: `auth.get_credentials()`, `config.TARGET_CALENDAR_ID`, `config.TIMEZONE`, `tools.Proposal`
- Produces: `writer.WriteResult` (`NamedTuple`: `created: list[str]`, `failed: list[tuple[str, str]]`), `writer.to_google_event(block: dict) -> dict`, `writer.create_events(proposal: Proposal, calendar_id: str | None = None) -> WriteResult`

- [ ] **Step 1: Write the failing test**

Create `tests/test_writer.py`:

```python
from src.writer import to_google_event


def test_block_becomes_a_google_event_with_timezone():
    block = {"title": "Interview prep", "day": "2026-08-25",
             "start": "17:00", "end": "19:00", "reason": "first clear evening"}
    event = to_google_event(block)
    assert event["summary"] == "Interview prep"
    assert event["start"]["dateTime"].startswith("2026-08-25T17:00")
    assert event["end"]["dateTime"].startswith("2026-08-25T19:00")
    assert event["start"]["timeZone"] == "America/New_York"


def test_reason_is_carried_into_the_description():
    block = {"title": "Prep", "day": "2026-08-25", "start": "17:00",
             "end": "19:00", "reason": "first clear evening"}
    assert "first clear evening" in to_google_event(block)["description"]
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_writer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.writer'`

- [ ] **Step 3: Write src/writer.py**

```python
"""Create calendar events.

THIS IS THE ONLY MODULE THAT WRITES TO YOUR CALENDAR. The agent cannot
reach it — main.py calls create_events only after you approve.
"""
from typing import NamedTuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from src.auth import get_credentials
from src.tools import Proposal


class WriteResult(NamedTuple):
    created: list[str]
    failed: list[tuple[str, str]]     # (title, error message)


def to_google_event(block: dict) -> dict:
    """Convert one proposal block into the Google Calendar event body."""
    tz_name = str(config.TIMEZONE)
    return {
        "summary": block["title"],
        "description": f"Scheduled by CalAssist.\n\nWhy here: {block['reason']}",
        "start": {"dateTime": f"{block['day']}T{block['start']}:00", "timeZone": tz_name},
        "end": {"dateTime": f"{block['day']}T{block['end']}:00", "timeZone": tz_name},
    }


def create_events(proposal: Proposal, calendar_id: str | None = None) -> WriteResult:
    """Create every block. Reports partial failure rather than hiding it."""
    calendar_id = calendar_id or config.TARGET_CALENDAR_ID
    service = build("calendar", "v3", credentials=get_credentials())

    created, failed = [], []
    for block in proposal.blocks:
        try:
            service.events().insert(
                calendarId=calendar_id, body=to_google_event(block)
            ).execute()
            created.append(block["title"])
        except HttpError as exc:
            failed.append((block["title"], str(exc)))

    return WriteResult(created=created, failed=failed)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_writer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Verify the target is the test calendar**

```bash
python -c "import config; print('Writing to:', config.TARGET_CALENDAR_ID)"
```

Expected: your **CalAssist Test** calendar ID — not `primary`. If it says `primary`, fix `.env` before continuing.

- [ ] **Step 6: Commit**

```bash
git add src/writer.py tests/test_writer.py
git commit -m "feat: create calendar events with partial-failure reporting"
```

---

### Task 10: CLI wiring

**Files:**
- Create: `src/main.py`, `README.md`
- Test: end-to-end manual

**Interfaces:**
- Consumes: everything above
- Produces: `main.main() -> int`, console entry `python -m src.main plan [--write] [--week YYYY-MM-DD]`

- [ ] **Step 1: Write src/main.py**

```python
"""CalAssist CLI.

    python -m src.main plan              propose only, write nothing
    python -m src.main plan --write      propose, then offer to write
"""
import argparse
import sys
from datetime import date, datetime, timedelta

import config
from src.agent import opening_message, run_conversation
from src.calendar_read import fetch_events
from src.preview import render
from src.writer import create_events


def _target_monday(week_arg: str | None) -> date:
    if week_arg:
        return datetime.fromisoformat(week_arg).date()
    today = date.today()
    return today - timedelta(days=today.weekday())


def main() -> int:
    parser = argparse.ArgumentParser(prog="calassist")
    parser.add_argument("command", choices=["plan"])
    parser.add_argument("--write", action="store_true",
                        help="offer to create events (default is preview only)")
    parser.add_argument("--week", help="Monday of the target week, YYYY-MM-DD")
    args = parser.parse_args()

    monday = _target_monday(args.week)
    sunday = monday + timedelta(days=6)
    print(f"Planning {monday:%b %-d} - {sunday:%b %-d}\n")

    proposal = run_conversation(opening_message(monday))
    if proposal is None:
        print("No proposal made. Nothing was changed.")
        return 1

    start = datetime.combine(monday, datetime.min.time(), tzinfo=config.TIMEZONE)
    existing = fetch_events(start, start + timedelta(days=7))
    path = render(proposal, existing)

    print("\n" + "=" * 60)
    print(f"  {len(proposal.blocks)} blocks proposed")
    for b in proposal.blocks:
        day = datetime.fromisoformat(b["day"]).date()
        print(f"    {day:%a %m/%d}  {b['start']}-{b['end']}  {b['title']}")
    for s in proposal.skipped_already_scheduled:
        print(f"    skipped: {s['item']} (already on calendar)")
    for n in proposal.not_scheduled:
        print(f"    did NOT fit: {n['item']} - {n['why']}")
    for w in proposal.warnings:
        print(f"    warning: {w}")
    print(f"\n  Visual preview:  file://{path}")
    print("=" * 60 + "\n")

    if not args.write:
        print("Preview only. Re-run with --write to create these events.")
        return 0

    answer = input(f"Write {len(proposal.blocks)} events to "
                   f"{config.TARGET_CALENDAR_ID}? [y/N] ").strip().lower()
    if answer != "y":
        print("Nothing written.")
        return 0

    result = create_events(proposal)
    for title in result.created:
        print(f"  created: {title}")
    for title, err in result.failed:
        print(f"  FAILED:  {title} - {err}")

    if result.failed:
        print(f"\n{len(result.created)} created, {len(result.failed)} failed.")
        return 1
    print(f"\n{len(result.created)} events created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the full flow, preview only**

```bash
python -m src.main plan
```

Expected: conversation → summary → a `file://` link → "Preview only." **Nothing is created.** Open the link and confirm the grid respects work hours, buffers, and dedupe.

- [ ] **Step 3: Run the full flow with writing**

```bash
python -m src.main plan --write
```

Expected: same, then a `[y/N]` prompt. Answer `y`. Check your **CalAssist Test** calendar in a browser — the events are there, each with a "Why here:" description.

- [ ] **Step 4: Verify the safety property**

```bash
grep -rn "events().insert\|events().update\|events().delete" src/
```

Expected: exactly one match, in `src/writer.py`. If any appears in `tools.py` or `agent.py`, the agent has gained write access and it must be removed.

- [ ] **Step 5: Write README.md**

```markdown
# CalAssist

A local AI agent that reads my weekly priorities doc and Google Calendar,
asks what it needs to know, and proposes a week I approve in one step.

## Setup

    uv venv --python 3.12 && source .venv/bin/activate
    uv pip install -r requirements.txt
    cp .env.example .env      # fill in doc IDs, calendar ID, API key

Google OAuth: see `docs/superpowers/plans/2026-08-23-calassist-v1.md` Task 2.
Place `credentials.json` in the project root, then:

    python -m src.auth        # opens a browser, creates token.json

## Usage

    python -m src.main plan            # propose, write nothing
    python -m src.main plan --write    # propose, then ask before writing

## Priorities doc format

    ## Week of 8.24

    ### Priorities
    1. NVIDIA interview prep - 4h
    2. Q4 roadmap draft - 3h

    ### Already scheduled
    - Dentist - Tue 2pm

    ### To-dos
    - Submit expenses (by Fri)

Time estimates drive scheduling. Numbered order decides what gets cut.
Anything missing, CalAssist asks about.

## How it stays safe

The agent has read-only tools. Only `src/writer.py` creates events, and only
after you answer `y`. Until you trust it, `CALASSIST_CALENDAR_ID` points at a
throwaway "CalAssist Test" calendar.

## Known gotcha

If the Google Cloud OAuth app is left in "Testing" status, refresh tokens
expire every 7 days. Publish the app to production (APIs & Services > OAuth
consent screen > Publish app) and click past the unverified-app warning once.

## Costs

Google APIs are free. Claude usage is about $0.11 per session on
`claude-sonnet-5` — roughly $6/year at weekly use.
```

- [ ] **Step 6: Run the whole suite**

```bash
python -m pytest -v
```

Expected: 32 passed.

- [ ] **Step 7: Commit**

```bash
git add src/main.py README.md
git commit -m "feat: CLI with preview-by-default and gated writing"
```

---

### Task 11: Pre-publication audit (run before making the repo public)

Everything up to here prevents a *future* leak. This task proves no leak has
*already* happened. Deleting a file does not remove it from git history — a
secret committed in Task 3 and deleted in Task 4 is still fully readable in
the published repo.

**Files:** none created — this is a verification gate.

- [ ] **Step 1: Install gitleaks and scan full history**

```bash
brew install gitleaks
cd ~/Projects/calassist
gitleaks detect --source . --log-opts="--all" --verbose
```

Expected: `no leaks found`. **If it reports anything, stop.** Do not publish.
Rotate the exposed credential first (SECURITY.md), then decide whether to
scrub history or start a fresh repo — for a young project, starting fresh is
usually faster and safer than `git filter-repo`.

- [ ] **Step 2: Check every filename that has ever existed**

```bash
git log --all --full-history --name-only --format="" \
  | sort -u | grep -Ei 'token|credential|secret|\.env$|\.pem$|\.key$' || echo "CLEAN"
```

Expected: `CLEAN`, or only `.env.example` and `SECURITY.md`.

- [ ] **Step 3: Grep all history content for secret shapes**

```bash
git grep -nIE 'sk-ant-[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9_-]{20,}|"refresh_token"|"client_secret"|AIza[0-9A-Za-z_-]{35}' \
  $(git rev-list --all) -- 2>/dev/null || echo "CLEAN"
```

Expected: `CLEAN`.

- [ ] **Step 4: Confirm the working tree is clean**

```bash
python -m pytest tests/test_no_secrets_in_repo.py -v
git ls-files | grep -Ei 'token|credential|\.env$' || echo "CLEAN"
```

Expected: 4 passed, and `CLEAN`.

- [ ] **Step 5: Create the repo as PRIVATE first**

```bash
gh repo create calassist --private --source=. --remote=origin --push
```

Private first, deliberately. It gives you a window to inspect the pushed
result before the internet can see it.

- [ ] **Step 6: Enable GitHub's own protections**

In the repo on github.com → **Settings → Code security**:

- **Secret scanning** → Enable
- **Push protection** → Enable — this blocks a push containing a detected
  secret at the server, catching anything that slipped past your local hook
  (e.g. a commit made from another machine without the hook installed)

Then confirm the CI scan ran: **Actions** tab → `secret-scan` → green.

- [ ] **Step 7: Review what is actually published**

```bash
gh browse
```

Click through the file list yourself. Confirm you see `.env.example` with
placeholder values and **no** `token.json`, `credentials.json`, or `.env`.

- [ ] **Step 8: Flip to public**

Settings → General → Danger Zone → **Change visibility → Public**.

- [ ] **Step 9: Post-publication verification (within 5 minutes)**

```bash
cd /tmp && rm -rf calassist-audit
git clone https://github.com/<you>/calassist.git calassist-audit
cd calassist-audit
ls -a                                       # no secret files
gitleaks detect --source . --log-opts="--all"   # no leaks found
cd /tmp && rm -rf calassist-audit
```

Cloning fresh shows exactly what a stranger sees — the definitive check.

- [ ] **Step 10: Set a calendar reminder to rotate**

Rotate the Anthropic key every 90 days. In a public-repo project the cost of
rotation is near zero and it bounds the damage of a leak you never noticed.

---

## Verification

After Task 10, confirm each spec requirement end to end:

```bash
# 1. Full suite green
python -m pytest -v

# 2. Only one module can write
grep -rn "events().insert" src/          # exactly one hit: src/writer.py

# 3. No secret exists inside the repo at all
python -m pytest tests/test_no_secrets_in_repo.py -v
ls credentials.json token.json .env 2>&1   # all three: No such file

# 3b. History is clean (required before publishing)
gitleaks detect --source . --log-opts="--all"

# 4. Work hours never proposed
python -m src.main plan                  # every block is 17:00+ on a weekday

# 5. Dedupe announced
#    Put something in the doc that is already on your calendar.
#    It must appear under "skipped" — not as a second block.

# 6. Duration asked, not guessed
#    Remove a time estimate from a priority. CalAssist must ask.

# 7. Writes land on the test calendar only
python -m src.main plan --write
python -c "import config; print(config.TARGET_CALENDAR_ID)"
```

**Graduating to your real calendar:** once several weeks look right, change
`CALASSIST_CALENDAR_ID` in `.env` to `primary`. One line, no code change.

## Deferred to v2

Moving or deleting events; multi-week planning; the interactive web UI;
work-calendar integration; hosted deployment.
