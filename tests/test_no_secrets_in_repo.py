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
