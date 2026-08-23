"""Decide whether a reply means "yes, do it" or "change something".

An empty line meaning "accept" is not discoverable — people type "yes",
"looks good", "set". Treating those as revision requests silently drops them
into another agent turn and the calendar never gets written.
"""
import re

AFFIRMATIVES = {
    "y", "ye", "yes", "yep", "yeah", "yup", "yes please", "ok", "okay", "k",
    "sure", "fine", "good", "great", "perfect", "nice", "cool", "done", "set",
    "all set", "we're set", "were set", "accept", "accepted", "approve",
    "approved", "confirm", "confirmed", "go", "go ahead", "send it", "ship it",
    "do it", "lgtm", "looks good", "look good", "looks great", "looks right",
    "sounds good", "sounds great", "that works", "works for me", "im happy",
    "i'm happy", "happy", "happy with this", "yes happy with this",
    "add to calendar", "add it", "write it", "save it", "book it", "schedule it",
    "yes do it", "yes please do it", "finalize", "finalise", "push it",
    "love it", "i love it", "love this", "amazing", "awesome", "excellent",
    "beautiful", "exactly", "spot on", "thats it", "that's it", "thats great",
    "yes thank you", "thanks", "thank you", "correct", "right", "looks perfect",
    "put it on my calendar", "send it to my calendar", "save it to my calendar",
    "im good", "i'm good", "we're good", "were good", "no changes",
    "nothing to change", "no notes", "keep it", "as is", "leave it",
}

# Anything asking for a change, even wrapped in a "yes".
CHANGE_WORDS = re.compile(
    r"\b(move|change|swap|shift|instead|but|except|remove|delete|drop|add(?!\s+to\s+calendar)"
    r"|earlier|later|another|different|reschedule|make it|can you|could you"
    r"|rather|not?\s+the|push .* to|split|combine|shorter|longer)\b"
)


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", "", text.strip().lower()).strip()


# Phrases that contain a change word but mean the opposite.
NO_CHANGE = {"no changes", "nothing to change", "no change", "dont change anything",
             "don't change anything", "no notes", "nothing to add"}


def is_acceptance(text: str) -> bool:
    """True when the reply means 'yes, go ahead' rather than 'change this'."""
    cleaned = normalise(text)
    if not cleaned:
        return True                       # bare Enter still accepts
    if cleaned in NO_CHANGE:
        return True                       # says "change", means "don't"
    if CHANGE_WORDS.search(cleaned):
        return False                      # "yes but move the gym" is a change
    if cleaned in AFFIRMATIVES:
        return True
    # Short and starts affirmatively: "yes thanks", "ok great".
    words = cleaned.split()
    return len(words) <= 4 and words[0] in {
        "y", "yes", "yep", "yeah", "yup", "ok", "okay", "sure", "perfect",
        "great", "good", "done", "set", "accept", "approve", "confirm",
    }
