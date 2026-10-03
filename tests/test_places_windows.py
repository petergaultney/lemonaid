"""Closing planned windows, moving whoever is looking at them first."""

import subprocess
from pathlib import Path
from subprocess import CompletedProcess

from lemonaid.places import ownership, windows


def _pane(window: str, pane: str, path: str) -> ownership.Pane:
    return ownership.Pane("work", window, pane, Path(path))


def _tmux_answers(monkeypatch, answers: dict[str, str]) -> list[list[str]]:
    """Answer each tmux subcommand from *answers*; record every call."""
    calls: list[list[str]] = []

    def _run(argv, **kwargs):
        calls.append(argv)
        return CompletedProcess(argv, 0, answers.get(argv[1], ""), "")

    monkeypatch.setattr(windows.subprocess, "run", _run)
    return calls


def test_clients_on_a_doomed_window_move_to_a_surviving_one(monkeypatch):
    calls = _tmux_answers(
        monkeypatch,
        {
            "list-clients": "/dev/ttys001\tkatamari\t@4\n/dev/ttys002\tkatamari\t@1\n",
            "list-windows": "@1\n@4\n@7\n",
        },
    )

    assert windows.move_clients_off(["@4", "@7"]) == ""

    switches = [c for c in calls if c[1] == "switch-client"]
    assert switches == [["tmux", "switch-client", "-c", "/dev/ttys001", "-t", "@1"]]


def test_a_client_with_nowhere_to_go_stops_the_close(monkeypatch):
    _tmux_answers(
        monkeypatch,
        {"list-clients": "/dev/ttys001\twork\t@4\n", "list-windows": "@4\n"},
    )

    why = windows.move_clients_off(["@4"])

    assert "Nowhere in 'work'" in why
    assert "nothing was closed" in why


def test_an_unanswered_client_query_refuses_to_close(monkeypatch):
    """Not knowing who is looking is not the same as nobody looking."""

    def _run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 5)

    monkeypatch.setattr(windows.subprocess, "run", _run)

    why = windows.move_clients_off(["@4"])

    assert "Could not tell who is looking" in why
    assert "nothing was closed" in why


def test_an_unanswered_window_listing_strands_the_client(monkeypatch):
    def _run(argv, **kwargs):
        if argv[1] == "list-windows":
            raise OSError("tmux went away")
        return CompletedProcess(argv, 0, "/dev/ttys001\twork\t@4\n", "")

    monkeypatch.setattr(windows.subprocess, "run", _run)

    assert "Nowhere in 'work'" in windows.move_clients_off(["@4"])


def test_no_clients_means_nothing_to_move(monkeypatch):
    calls = _tmux_answers(monkeypatch, {"list-clients": ""})

    assert windows.move_clients_off(["@4"]) == ""
    assert [c[1] for c in calls] == ["list-clients"]


def test_own_window_comes_from_the_pane_in_the_environment(monkeypatch):
    monkeypatch.setenv("TMUX_PANE", "%12")
    calls = _tmux_answers(monkeypatch, {"display-message": "@3\n"})

    assert windows.own_window() == "@3"
    assert calls[0][:5] == ["tmux", "display-message", "-p", "-t", "%12"]


def test_own_window_is_empty_outside_tmux(monkeypatch):
    monkeypatch.delenv("TMUX_PANE", raising=False)

    assert windows.own_window() == ""


def test_close_kills_each_window_and_reports_the_stubborn(monkeypatch):
    def _run(argv, **kwargs):
        if argv[-1] == "@7":
            raise OSError("no such window")
        return CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(windows.subprocess, "run", _run)

    assert windows.close(["@4", "@7", "@9"]) == ["@7"]


def test_ttys_are_gathered_per_window(monkeypatch):
    _tmux_answers(monkeypatch, {"list-panes": "/dev/ttys004\n/dev/ttys005\n"})

    assert windows.ttys(["@4"]) == {"/dev/ttys004", "/dev/ttys005"}
    assert windows.ttys([]) == set()


def test_ttys_of_a_window_tmux_will_not_describe_are_none(monkeypatch):
    def _run(argv, **kwargs):
        raise OSError("tmux went away")

    monkeypatch.setattr(windows.subprocess, "run", _run)

    assert windows.ttys(["@4"]) == set()
