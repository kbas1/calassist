import io

from src.status import TOOL_LABELS, Spinner


def test_every_tool_has_a_human_label():
    from src.tools import ALL_TOOLS
    for tool in ALL_TOOLS:
        assert tool.name in TOOL_LABELS, f"no status label for {tool.name}"


def test_spinner_is_inert_when_not_a_terminal():
    """Piped output and CI must not get escape codes."""
    buf = io.StringIO()                      # StringIO.isatty() is False
    with Spinner("thinking", stream=buf) as sp:
        sp.update("reading your calendar")
    assert buf.getvalue() == ""


def test_spinner_context_manager_returns_itself():
    buf = io.StringIO()
    with Spinner(stream=buf) as sp:
        assert isinstance(sp, Spinner)
