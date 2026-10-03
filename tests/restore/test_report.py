"""Waiting for restored lemons, and what each one is reported as."""

import pytest

from lemonaid.restore import report

_STARTED = 1000.0
_RUNNING = report.Seen(True, "")


@pytest.fixture
def clock(monkeypatch) -> list[float]:
    """A clock that moves only when `wait` sleeps."""
    now = [_STARTED]
    monkeypatch.setattr(report.time, "time", lambda: now[0])
    monkeypatch.setattr(report.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    return now


def _lemon(channel: str = "claude:a", rearm: str = report.PROMPTED) -> report.Placed:
    return report.Placed(channel, f"lemon {channel}", f"work:{channel[-1]}", rearm)


def _wait(lemons, activity, inspect, wait: float = 60.0, progress=None) -> list[report.Result]:
    return report.wait(
        lemons,
        _STARTED,
        _STARTED + wait,
        activity,
        inspect,
        progress if progress is not None else (lambda _: None),
    )


def test_a_prompted_lemon_the_inbox_hears_from_is_working(clock):
    heard = {"claude:a": 0.0}

    def activity():
        if clock[0] >= _STARTED + 10:
            heard["claude:a"] = clock[0]
        return heard

    [result] = _wait([_lemon()], activity, lambda _: _RUNNING)

    assert result.outcome == report.WORKING
    assert clock[0] < _STARTED + 60  # it stopped waiting once it had heard


def test_activity_from_before_the_restore_does_not_count(clock):
    [result] = _wait([_lemon()], lambda: {"claude:a": _STARTED - 1}, lambda _: _RUNNING)

    assert result.outcome == report.STUCK


def test_a_lemon_that_stays_silent_is_stuck_with_the_dialog_it_shows(clock):
    trust = report.Seen(True, "> Trust this folder?\n  1. Yes, continue\n")

    [result] = _wait([_lemon("codex:b")], dict, lambda _: trust)

    assert result.outcome == report.STUCK
    assert result.detail == "Codex's folder-trust prompt"


def test_a_harness_that_exits_to_the_shell_is_exited_with_its_last_lines(clock):
    gone = report.Seen(False, "Please restart Codex.\n\n$ \n")

    [result] = _wait([_lemon("codex:b")], dict, lambda _: gone)

    assert result.outcome == report.EXITED
    assert "Please restart Codex." in result.detail
    assert clock[0] < _STARTED + 60  # an exit settles it before the deadline


def test_a_pane_is_not_exited_before_its_shell_has_had_time_to_start_the_line(clock):
    def inspect(_):
        return _RUNNING if clock[0] > _STARTED else report.Seen(False, "")

    [result] = _wait([_lemon()], dict, inspect, wait=30)

    assert result.outcome == report.STUCK


def test_a_lemon_without_a_prompt_is_reported_by_why_and_not_waited_for(clock):
    [no_brief, nothing] = _wait(
        [_lemon("claude:a", report.NO_BRIEF), _lemon("claude:b", report.NOTHING_TO_REARM)],
        dict,
        lambda _: _RUNNING,
    )

    assert (no_brief.outcome, nothing.outcome) == (report.NO_BRIEF, report.NOTHING_TO_REARM)
    assert clock[0] == _STARTED


def test_progress_is_printed_while_it_waits(clock):
    lines: list[str] = []

    _wait([_lemon()], dict, lambda _: _RUNNING, wait=12, progress=lines.append)

    assert lines and "waiting on 1" in lines[0]


def test_results_keep_the_order_the_lemons_were_placed_in(clock):
    lemons = [_lemon("claude:a"), _lemon("claude:b", report.NO_BRIEF), _lemon("claude:c")]

    results = _wait(lemons, lambda: {"claude:c": clock[0]}, lambda _: _RUNNING, wait=10)

    assert [r.channel for r in results] == ["claude:a", "claude:b", "claude:c"]
    assert [r.outcome for r in results] == [report.STUCK, report.NO_BRIEF, report.WORKING]


def test_a_lemon_to_rearm_by_hand_is_not_ok(clock):
    [result] = _wait([_lemon("opencode:a", report.BY_HAND)], dict, lambda _: _RUNNING)

    assert result.outcome == report.BY_HAND
    assert result.outcome not in report.OK
