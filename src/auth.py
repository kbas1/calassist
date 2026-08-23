"""Google OAuth for CalAssist.

Two files do the work, and BOTH live in ~/.config/calassist/, never in this
repository:
  credentials.json  the app's ID badge (downloaded from Cloud console)
  token.json        YOUR access key, created on first run - password equivalent

This repo is public. Keeping these outside the working tree means git cannot
see them at all - stronger than relying on .gitignore.

Revoke anytime: myaccount.google.com > Security > Third-party apps.
"""
import json
import stat

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import config

# ONE scope, and it is the narrowest that does the job.
#
# We deliberately do NOT request documents.readonly: Google's Docs API has no
# per-document scope, so reading one priorities doc would have granted read
# access to EVERY document in the account. Priorities are read from a local
# file instead (see config.PRIORITIES_FILE) — zero Google Docs access.
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
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


def _load_existing() -> Credentials | None:
    """Load token.json, tolerating a corrupt or unreadable file."""
    if not TOKEN_FILE.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except (ValueError, KeyError, json.JSONDecodeError):
        # Corrupt or hand-edited token file — discard and re-authorize.
        TOKEN_FILE.unlink(missing_ok=True)
        return None


def _browser_flow() -> Credentials:
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"{CREDENTIALS_FILE} not found. Download it from the Google "
            "Cloud console (APIs & Services > Credentials > OAuth client "
            "ID > Desktop app) and move it there - NOT into this repo."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    return flow.run_local_server(port=0)             # opens browser


def get_credentials() -> Credentials:
    """Return valid credentials, re-authorizing in a browser when necessary.

    This app is registered in Google's "Testing" publishing status, where
    refresh tokens expire every 7 days. That is expected, not an error — so a
    failed refresh silently falls back to the browser flow instead of raising
    a confusing invalid_grant traceback at the user.
    """
    creds = _load_existing()

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())                 # silent renewal
            _write_private(TOKEN_FILE, creds.to_json())
            return creds
        except RefreshError:
            print(
                "Google authorization has expired (apps in Testing status expire "
                "every 7 days).\nRe-opening your browser — click Allow once and "
                "this will continue.\n"
            )
            TOKEN_FILE.unlink(missing_ok=True)

    creds = _browser_flow()
    _write_private(TOKEN_FILE, creds.to_json())
    return creds


if __name__ == "__main__":
    from googleapiclient.discovery import build

    service = build("calendar", "v3", credentials=get_credentials())
    calendars = service.calendarList().list().execute().get("items", [])
    print(f"Authenticated. {len(calendars)} calendars visible:\n")
    for cal in calendars:
        primary = " (primary)" if cal.get("primary") else ""
        print(f"  {cal['summary']}{primary}")
        print(f"      id: {cal['id']}")
