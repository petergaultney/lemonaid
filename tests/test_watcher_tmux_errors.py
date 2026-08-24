"""A tmux that cannot answer is not a pane that is gone.

`get_pane_for_tty` used to swallow a CalledProcessError and return (None, None),
which the auto-archiver reads as "this pane no longer exists". One failed
`tmux list-panes` therefore looked exactly like every pane having disappeared at
once, and retired every live session in the inbox. Only an answer is allowed to
archive something; an error has to leave the session alone.
"""

import subprocess

import pytest

from lemonaid import handlers
from lemonaid.lemon_watchers import watcher
from lemonaid.tmux import navigation


def _tmux_fails(monkeypatch) -> None:
    def _run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(subprocess, "run", _run)


def _tmux_lists(monkeypatch, *rows: str) -> None:
    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="\n".join(rows) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)


def test_a_failed_lookup_is_raised_not_reported_as_absent(monkeypatch):
    _tmux_fails(monkeypatch)

    with pytest.raises(navigation.TmuxUnavailable):
        navigation.get_pane_for_tty("/dev/ttys001")


def test_an_unknown_tty_is_still_absent(monkeypatch):
    _tmux_lists(monkeypatch, "/dev/ttys002|work|%3")

    assert navigation.get_pane_for_tty("/dev/ttys001") == (None, None)


def test_pane_existence_is_unknown_when_tmux_fails(monkeypatch):
    _tmux_fails(monkeypatch)

    assert handlers.check_pane_exists_by_tty("/dev/ttys001", "tmux") is None


def test_pane_existence_is_false_when_tmux_answers(monkeypatch):
    _tmux_lists(monkeypatch, "/dev/ttys002|work|%3")

    assert handlers.check_pane_exists_by_tty("/dev/ttys001", "tmux") is False


def test_the_watcher_keeps_a_session_whose_pane_it_cannot_check(monkeypatch):
    """The case that archived a whole inbox: assume alive, not gone."""
    _tmux_fails(monkeypatch)

    assert watcher._check_pane_exists("/dev/ttys001", "tmux")


def test_the_watcher_still_archives_a_pane_that_is_really_gone(monkeypatch):
    _tmux_lists(monkeypatch, "/dev/ttys002|work|%3")

    assert not watcher._check_pane_exists("/dev/ttys001", "tmux")


def test_a_tmux_error_archives_nothing(monkeypatch):
    """End to end: the archiver sees every session as still live."""
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name="claude": True)
    _tmux_fails(monkeypatch)

    archived: list[str] = []
    watcher._archive_stale_sessions(
        [
            ("claude:a", "sid", "/work/one", 1.0, False, "/dev/ttys001", "msg", "tmux"),
            ("claude:b", "sid", "/work/two", 2.0, False, "/dev/ttys002", "msg", "tmux"),
        ],
        archived.append,
    )

    assert archived == []
