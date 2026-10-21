from lemonaid import handlers
from lemonaid.config import Config, TuiConfig
from lemonaid.inbox import db
from lemonaid.inbox.tui.switching import double_activate
from lemonaid.tmux import keep_focus


def test_second_activation_of_same_row_inside_window_is_double():
    assert double_activate.is_double(("7", 10.0), "7", 10.3, 400)


def test_activation_after_window_is_single():
    assert not double_activate.is_double(("7", 10.0), "7", 10.5, 400)


def test_other_row_or_no_previous_is_single():
    assert not double_activate.is_double(("7", 10.0), "8", 10.1, 400)
    assert not double_activate.is_double(None, "7", 10.1, 400)


def test_window_follows_the_configured_milliseconds():
    assert double_activate.is_double(("7", 10.0), "7", 10.9, 1000)
    assert not double_activate.is_double(("7", 10.0), "7", 10.9, 800)


def test_mode_is_off_by_default():
    assert not TuiConfig().double_activate_focus
    assert TuiConfig().double_activate_ms == 400


def _notification() -> db.Notification:
    return db.Notification(
        id=1,
        channel="claude:abc",
        name="n",
        message="",
        switch_source="tmux",
        metadata={},
    )


def _fake_tmux(monkeypatch, located) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setenv("TMUX_PANE", "%1")
    monkeypatch.setattr(keep_focus.recorded_pane, "locate", lambda _m: located)
    monkeypatch.setattr(keep_focus.follow, "publish", lambda _o: None)
    monkeypatch.setattr(handlers, "handle_notification", lambda *_a, **_k: True)
    monkeypatch.setattr(keep_focus.subprocess, "run", lambda argv, **_k: calls.append(argv))
    return calls


def test_existing_pane_is_shown_and_inbox_pane_reselected(monkeypatch):
    calls = _fake_tmux(monkeypatch, ("s", "%9"))

    assert double_activate.show_keeping_focus(_notification(), Config())
    assert calls == [["tmux", "select-pane", "-t", "%1"]]


def test_missing_pane_is_left_to_the_resuming_path(monkeypatch):
    calls = _fake_tmux(monkeypatch, (None, None))

    assert not double_activate.show_keeping_focus(_notification(), Config())
    assert calls == []


def test_focus_change_right_after_a_show_is_its_own_round_trip():
    assert double_activate.is_own_focus_cycle(("7", 10.0), 10.1, 400)


def test_focus_change_later_or_with_no_show_is_the_user():
    assert not double_activate.is_own_focus_cycle(("7", 10.0), 10.6, 400)
    assert not double_activate.is_own_focus_cycle(None, 10.1, 400)
