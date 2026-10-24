"""Several rows on one tty with a live Claude: the session Claude names keeps it."""

from lemonaid.lemon_watchers import watcher

_TTY = "/dev/ttys001"
_PANES = {None: {_TTY: ("hq", "1")}}
_LIVE = {"ttys001": ["claude --resume real-hq"]}


def _row(channel: str, session_id: str) -> tuple:
    return (channel, session_id, "/tmp", 0.0, False, _TTY, "message", "tmux")


_ROWS = [
    _row("claude:real", "real-hq"),
    _row("claude:quit1", "quit-1"),
    _row("claude:quit2", "quit-2"),
]


def _archive(claude_sessions) -> list[str]:
    archived: list[str] = []
    watcher._archive_stale_sessions(
        _ROWS, archived.append, {}, _PANES, tty_processes=_LIVE, claude_sessions=claude_sessions
    )
    return archived


def test_sessions_started_and_quit_in_a_pane_are_archived_once_another_runs_there():
    assert sorted(_archive(lambda: {_TTY: {"real-hq"}})) == ["claude:quit1", "claude:quit2"]


def test_every_row_is_kept_when_claude_names_none_of_them():
    assert _archive(lambda: {_TTY: {"someone-else"}}) == []


def test_every_row_is_kept_when_the_sessions_cannot_be_listed():
    assert _archive(lambda: None) == []
    assert _archive(None) == []
