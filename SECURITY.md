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

    .../auth/calendar             read + write events
    .../auth/documents.readonly   read docs only

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

Run the checklist in `docs/superpowers/plans/2026-08-23-calassist-v1.md`,
Task 11.
