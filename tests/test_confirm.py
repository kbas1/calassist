import pytest

from src.confirm import is_acceptance


@pytest.mark.parametrize("reply", [
    "", "  ", "y", "yes", "Yes", "yep", "ok", "OK!", "sure", "looks good",
    "sounds good", "perfect", "set", "all set", "done", "accept", "approve",
    "yes happy with this", "add to calendar", "go ahead", "lgtm",
    "yes thanks", "ok great", "book it", "finalize",
    "love it", "I love it", "amazing", "awesome", "exactly", "that's it",
    "thank you", "no changes", "nothing to change", "keep it", "leave it",
    "put it on my calendar", "I'm good", "no notes",
])
def test_accepts_natural_yeses(reply):
    assert is_acceptance(reply) is True, reply


@pytest.mark.parametrize("reply", [
    "move the gym to Tuesday",
    "yes but move the roadmap to Sunday",
    "can you shift the prep later",
    "make it shorter",
    "remove the travel block",
    "swap Tuesday and Thursday",
    "put the Discover call earlier",
    "looks good except the gym",
    "add a second gym session",
    "I'd rather do it Saturday",
])
def test_rejects_change_requests(reply):
    assert is_acceptance(reply) is False, reply


def test_yes_wrapping_a_change_is_still_a_change():
    """The most dangerous case — an affirmative prefix hiding an edit."""
    assert is_acceptance("yes but move the gym") is False
