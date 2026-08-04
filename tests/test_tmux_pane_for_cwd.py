"""Resolving a pane from a directory, and refusing when that is ambiguous.

A directory does not identify a session. Two agents started in one worktree at
different times both match it, as does any other session with a window open
there. Taking the first match sends you somewhere unrelated and reads as a
switching bug, so the ambiguous case is reported rather than guessed.
"""

import subprocess

from lemonaid.tmux import navigation


def _panes(monkeypatch, *rows: str) -> None:
    """Stand in for `tmux list-panes -a` with cwd|cmd|session|pane_id rows."""

    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="\n".join(rows) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)


def _fails(monkeypatch) -> None:
    def _run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(subprocess, "run", _run)


def test_one_pane_at_the_directory(monkeypatch):
    _panes(monkeypatch, "/work/feat|claude|feat|%3")

    assert navigation.get_pane_for_cwd("/work/feat") == ("feat", "%3")


def test_no_pane_there(monkeypatch):
    _panes(monkeypatch, "/work/other|claude|other|%1")

    assert navigation.get_pane_for_cwd("/work/feat") == (None, None)


def test_several_panes_in_one_session_take_the_first(monkeypatch):
    """Ambiguity is about sessions, not panes - a session's own windows are fine."""
    _panes(
        monkeypatch,
        "/work/feat|emacsclient|feat|%1",
        "/work/feat|claude|feat|%2",
    )

    assert navigation.get_pane_for_cwd("/work/feat") == ("feat", "%1")


def test_two_sessions_at_one_directory_is_refused(monkeypatch):
    """The case behind switching to the wrong session."""
    _panes(
        monkeypatch,
        "/work/feat|claude|feat|%1",
        "/work/feat|claude|onlooker|%9",
    )

    session, pane_id = navigation.get_pane_for_cwd("/work/feat")

    assert session == navigation.AMBIGUOUS
    assert pane_id is None


def test_the_process_filter_can_resolve_ambiguity(monkeypatch):
    """Only one of the two is running the agent, so there is no real contest."""
    _panes(
        monkeypatch,
        "/work/feat|claude|feat|%1",
        "/work/feat|zsh|onlooker|%9",
    )

    assert navigation.get_pane_for_cwd("/work/feat", "claude") == ("feat", "%1")


def test_the_process_filter_narrowing_to_nothing_is_not_ambiguous(monkeypatch):
    _panes(monkeypatch, "/work/feat|zsh|onlooker|%9")

    assert navigation.get_pane_for_cwd("/work/feat", "claude") == (None, None)


def test_a_failed_tmux_call_is_not_ambiguous(monkeypatch):
    """It must read as 'unknown', not as 'several' - the responses differ."""
    _fails(monkeypatch)

    assert navigation.get_pane_for_cwd("/work/feat") == (None, None)


def test_malformed_rows_are_skipped(monkeypatch):
    _panes(monkeypatch, "garbage", "/work/feat|claude|feat|%3", "|||")

    assert navigation.get_pane_for_cwd("/work/feat") == ("feat", "%3")
