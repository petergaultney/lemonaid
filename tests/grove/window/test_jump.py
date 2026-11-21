from lemonaid import go, handlers
from lemonaid.config import load_config
from lemonaid.grove.window import data
from lemonaid.inbox import db, ended


def _jump(monkeypatch, source: str, problem: str = "", pane: bool | None = True, lost=False):
    with db.connect() as conn:
        db.add(conn, "claude:j", "hi", "jumper", {"tty": "/dev/ttys777"}, switch_source=source)
    went = []
    monkeypatch.setattr(go, "jump_problems", lambda rows: {"claude:j": problem} if problem else {})
    monkeypatch.setattr(ended, "lost", lambda _metadata: lost)
    monkeypatch.setattr(handlers, "check_pane_exists_by_tty", lambda *_args: pane)
    monkeypatch.setattr(go, "jump_tmux", lambda found, client: went.append(("tmux", client)))
    monkeypatch.setattr(
        handlers,
        "handle_notification",
        lambda metadata, _config, switch_source: went.append((switch_source, metadata["channel"]))
        or True,
    )
    return data.jump("claude:j", "/dev/ttys004", load_config()), went


def test_a_tmux_lemon_in_its_pane_switches_the_client_the_window_was_summoned_over(monkeypatch):
    assert _jump(monkeypatch, "tmux") == ("", [("tmux", "/dev/ttys004")])


def test_a_tmux_lemon_whose_pane_is_gone_is_resumed_by_its_front_end(monkeypatch):
    assert _jump(monkeypatch, "tmux", "pane gone", pane=False) == ("", [("tmux", "claude:j")])


def test_a_lemon_lost_with_its_server_or_in_a_pane_that_cant_be_told_apart_is_not_resumed(
    monkeypatch,
):
    lost = _jump(monkeypatch, "tmux", "lost with its tmux server", pane=False, lost=True)
    assert lost == ("Can't jump to jumper: lost with its tmux server", [])
    assert _jump(monkeypatch, "tmux", "ambiguous", pane=True)[1] == []
    assert _jump(monkeypatch, "tmux", "can't check", pane=None)[1] == []


def test_a_lemon_in_another_terminal_is_shown_by_its_front_end(monkeypatch):
    assert _jump(monkeypatch, "wezterm", pane=None)[1] == [("wezterm", "claude:j")]
    assert _jump(monkeypatch, "cmux", pane=None)[1] == [("cmux", "claude:j")]


def test_a_front_end_that_cant_show_the_lemon_says_so(monkeypatch):
    with db.connect() as conn:
        db.add(conn, "claude:k", "hi", "stuck", {}, switch_source="wezterm")
    monkeypatch.setattr(handlers, "handle_notification", lambda *_args, **_kw: False)

    assert data.jump("claude:k", "", load_config()) == "Could not switch to stuck"
