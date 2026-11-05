from lemonaid import front_end
from lemonaid.front_end import pick


def test_each_recorded_switch_source_names_its_front_end():
    assert [pick.named(name).terminal.name for name in ("tmux", "wezterm", "cmux")] == [
        "tmux",
        "wezterm",
        "cmux",
    ]
    assert pick.named("plain") is None
    assert pick.named(None) is None


def test_cmux_cant_prompt_a_lemon():
    assert pick.named("cmux").prompt is None
    assert pick.named("wezterm").prompt is not None


def test_a_tmux_session_inside_cmux_is_tmux(monkeypatch):
    monkeypatch.setattr(front_end.tmux.window, "own_session", lambda: "work")
    monkeypatch.setenv("CMUX_SURFACE_ID", "S1")

    assert pick.around_caller().terminal.name == "tmux"


def test_nowhere_beside_a_caller_outside_every_front_end(monkeypatch):
    monkeypatch.setattr(front_end.tmux.window, "own_session", lambda: "")
    for variable in ("WEZTERM_PANE", "CMUX_SURFACE_ID"):
        monkeypatch.delenv(variable, raising=False)

    assert pick.around_caller() is None
