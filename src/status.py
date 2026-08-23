"""A terminal status line, so a long silence never looks like a hang."""
import itertools
import sys
import threading
import time

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# What each tool is actually doing, in words the user recognises.
TOOL_LABELS = {
    "get_priorities": "reading your priorities",
    "get_calendar_events": "reading your calendar",
    "find_free_slots_tool": "finding open time",
    "submit_proposal": "putting the week together",
}


class Spinner:
    """Animates a single line until stopped. No-op when not a terminal."""

    def __init__(self, text: str = "thinking", stream=None):
        self.stream = stream or sys.stdout
        self.text = text
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = 0.0
        self.enabled = self.stream.isatty()

    def _run(self) -> None:
        for frame in itertools.cycle(FRAMES):
            if self._stop.is_set():
                return
            elapsed = int(time.monotonic() - self._started)
            self.stream.write(f"\r\033[K  {frame}  {self.text}… {elapsed}s")
            self.stream.flush()
            time.sleep(0.1)

    def clear(self) -> None:
        """Wipe the status line so other output starts clean."""
        if self.enabled:
            self.stream.write("\r\033[K")
            self.stream.flush()

    def update(self, text: str) -> None:
        self.text = text

    def __enter__(self) -> "Spinner":
        self._started = time.monotonic()
        if self.enabled:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.3)
        self.clear()
