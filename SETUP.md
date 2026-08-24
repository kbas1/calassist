# Setting up CalAssist

You need your own Google project and your own Claude key — nothing is shared
with whoever wrote this. Budget about 20 minutes, most of it clicking through
Google's console.

Everything Google-side is free. The only cost is Claude usage, roughly
$0.11 per weekly session.

---

## 1. Get the code running (5 min)

```bash
git clone https://github.com/kbas1/calassist.git
cd calassist

uv venv --python 3.12 && source .venv/bin/activate
uv pip install -r requirements.txt
```

No `uv`? Use `python3 -m venv .venv && source .venv/bin/activate` and
`pip install -r requirements.txt` instead.

Make the folder your secrets will live in — **outside the repo**, so git can
never see them:

```bash
mkdir -p ~/.config/calassist && chmod 700 ~/.config/calassist
git config core.hooksPath .githooks     # blocks commits containing secrets
```

## 2. Create a Google project (10 min)

In a browser, signed in as **the Google account whose calendar you want
managed**.

1. **console.cloud.google.com** → project dropdown (top left) → **New Project**
   → name it `calassist` → **Create**. Wait for it to switch to the new project.
2. **APIs & Services → Library** → search **Google Calendar API** → **Enable**.
3. Left sidebar → **OAuth consent screen** (newer accounts show
   **Google Auth Platform**) → choose **External** → **Create**.
4. On the **Branding** page fill in only:
   - App name: `CalAssist`
   - User support email: your address
   - Developer contact email: your address

   **Leave the App domain section completely blank.** Filling in a homepage or
   privacy policy URL makes Google demand a verified domain you do not have.
   Do not upload a logo — that triggers a review process. **Save.**
5. Left sidebar → **Audience** → **Test users** → **+ ADD USERS** → add your own
   email → **Save**.
6. Left sidebar → **Credentials** → **+ Create Credentials** →
   **OAuth client ID** → Application type **Desktop app** → **Create** →
   **DOWNLOAD JSON** in the popup.

   Miss the popup? The client now appears in a list — use the ⬇ icon on its row.

Move the downloaded file into place, renaming it:

```bash
mv ~/Downloads/client_secret_*.json ~/.config/calassist/credentials.json
chmod 600 ~/.config/calassist/credentials.json
```

> **About test-user mode:** Google expires your login every 7 days while the
> app is in "Testing". CalAssist handles this — it reopens the browser and you
> click once. Publishing to production avoids it but requires a hosted privacy
> policy and a domain Google can verify, which is rarely worth it for one user.

## 3. Make a calendar to write to (2 min)

Use a throwaway calendar until you trust it.

Google Calendar → left sidebar → **Other calendars → +** → **Create new
calendar** → name it `CalAssist` → **Create**. Then its **Settings** →
**Integrate calendar** → copy the **Calendar ID**.

## 4. Fill in your settings (3 min)

```bash
cp .env.example ~/.config/calassist/env
chmod 600 ~/.config/calassist/env
```

Open `~/.config/calassist/env` and set:

| Setting | What to put |
|---|---|
| `ANTHROPIC_API_KEY` | A key from console.anthropic.com |
| `CALASSIST_CALENDAR_ID` | The Calendar ID from step 3 |
| `READ_CALENDAR_IDS` | Calendars to read — see below |
| `PRIORITIES_FILE` | Where your weekly priorities live |

**Reading more than one calendar.** Comma-separated, no spaces after commas:

```
READ_CALENDAR_IDS=primary,you@work.com,family@group.calendar.google.com
```

`primary` is your main calendar. Add a work calendar if the same Google account
can see it — CalAssist will treat those events as busy time and plan around
them. A calendar it cannot read is skipped with a warning rather than crashing.

> ⚠️ **If your work calendar is on a different Google account, CalAssist cannot
> see it.** That is the situation `config.py` handles with `WEEKDAY_BLOCKED` —
> office hours are blocked by rule instead. Set that to your real working hours,
> or CalAssist will schedule deep work while you are at your desk.

## 5. Set your own hours (2 min)

`config.py` is written for one person's life. Change these:

```python
TIMEZONE        = ZoneInfo("America/New_York")
OWNER_NAME      = "Khushi"                 # appears on the chart
WEEKDAY_BLOCKED = (time(8, 30), time(17, 0))   # work — blocked by rule
WEEKDAY_BOOKABLE = [(time(17, 0), time(21, 0))]
WEEKEND_BOOKABLE = [(time(9, 0), time(21, 0))]
HOME_ADDRESS    = "..."      # used to estimate commute
OFFICE_ADDRESS  = "..."
```

## 6. Authorise and run

```bash
python -m src.auth
```

A browser opens. Pick your account. You will see **"Google hasn't verified
this app"** — that is expected, it is your own app. Click **Advanced** →
**Go to CalAssist (unsafe)** → **Allow**. Your calendars print in the terminal.

Then write your first priorities file (path from step 4):

```markdown
## Defaults
### Typical durations
- Gym session - 45m

## Week of 8.24
### Priorities
1. Interview prep - 4h
2. Roadmap draft - 3h

### To-dos
- Submit expenses (by Fri)
```

And plan a week:

```bash
python -m src.main plan          # propose only, writes nothing
python -m src.main plan --write  # propose, then ask before writing
```

Optional shortcuts:

```bash
echo "alias calassist='cd $(pwd) && source .venv/bin/activate && python -m src.main plan --write'" >> ~/.zshrc
source ~/.zshrc
```

---

## When it goes wrong

| Symptom | Cause |
|---|---|
| `Error 403: access_denied` | You are not in **Test users** (step 2.5) |
| `credentials.json not found` | File is in the repo, not `~/.config/calassist/` |
| `ModuleNotFoundError` | Virtual environment not active — `source .venv/bin/activate` |
| Asked to log in again after a week | Normal in Testing mode. Click through once |
| Nothing appears on your calendar | Tick the `CalAssist` checkbox in Google Calendar's sidebar |
| Blocks land during work hours | `WEEKDAY_BLOCKED` does not match your real hours |
| `warning: could not read calendar` | A `READ_CALENDAR_IDS` entry is wrong or not shared with you |

## Safety

Read [SECURITY.md](SECURITY.md). The short version: your credentials live in
`~/.config/calassist/`, never in the repo. The agent has read-only tools —
only `src/writer.py` creates events, and only after you confirm. Keep
`CALASSIST_CALENDAR_ID` pointed at a throwaway calendar until you trust it.
