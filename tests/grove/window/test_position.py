"""Where the window goes and whether it stays up, with macOS stood in for: the decisions in
`window/position.py`, which needs the `web` extra to import."""

import threading

import pytest

pytest.importorskip("webview")
pytest.importorskip("PyObjCTools")  # pywebview installs on Linux too; the window needs macOS

from lemonaid.config import load_config  # noqa: E402
from lemonaid.grove.window import api, position, settings  # noqa: E402

TERMINAL = [0, 0, 1000, 800]
DESK = "desk-displays"


class _Mac:
    """The window's frame and the terminal's, as `native` would report them, recording calls."""

    def __init__(self, monkeypatch, window_frame=TERMINAL, terminal=TERMINAL):
        self.frame, self.terminal, self.calls = list(window_frame), terminal, []
        native = position.native
        monkeypatch.setattr(native, "displays", lambda: DESK)
        monkeypatch.setattr(native, "frame_of", lambda _w: list(self.frame))
        monkeypatch.setattr(native, "terminal_frame", lambda app: app and self.terminal)
        monkeypatch.setattr(native, "put", lambda _w, placed: self._at(placed, "put"))
        monkeypatch.setattr(
            native, "cover", lambda _w, _app: self._at(self.terminal, "cover") or ""
        )
        monkeypatch.setattr(native, "focus", lambda _app: self.calls.append("focus"))
        monkeypatch.setattr(native, "hand_back", lambda _w, _app: self.calls.append("hide"))
        monkeypatch.setattr(position.AppHelper, "callAfter", lambda f, *args: f(*args))

    def _at(self, placed, how):
        self.frame = list(placed)
        self.calls.append(how)


class _Native:
    def __init__(self, visible):
        self.visible = visible

    def isVisible(self):
        return self.visible


class _Window:
    native = _Native(False)

    def __init__(self):
        self.js = []

    def run_js(self, js):
        self.js.append(js)


@pytest.fixture
def shared():
    return api.Shared(load_config(), terminal=object())


def test_with_nothing_kept_it_covers_the_terminal(monkeypatch, shared):
    mac = _Mac(monkeypatch, window_frame=[5, 5, 10, 10])

    position._place(_Window(), shared)
    assert (mac.calls, shared.over) == (["cover"], True)


def test_left_away_from_the_terminal_it_floats_there_and_stays_up_after_a_jump(monkeypatch, shared):
    mac = _Mac(monkeypatch)
    window = _Window()
    position._place(window, shared)

    mac.frame = [1200, 0, 600, 800]  # dragged onto another display
    position._remember(window, shared)
    assert settings.frame(DESK) == [1200, 0, 600, 800] and not shared.over

    mac.frame = [0, 0, 1, 1]
    position._place(window, shared)
    assert mac.frame == [1200, 0, 600, 800] and mac.calls[-1] == "put"
    position.leave(window, shared)
    assert mac.calls[-1] == "focus"


def test_left_over_the_terminal_it_covers_it_again_and_hides_after_a_jump(monkeypatch, shared):
    settings.keep_frame(DESK, [1200, 0, 600, 800])
    mac = _Mac(monkeypatch)
    window = _Window()
    position._place(window, shared)

    mac.frame = [800, 0, 600, 800]  # a fifth of the terminal
    position._remember(window, shared)
    assert settings.frame(DESK) is None and shared.over

    position.leave(window, shared)
    assert mac.calls[-1] == "hide"


def test_its_own_placement_and_a_move_while_displays_change_are_not_kept(monkeypatch, shared):
    mac = _Mac(monkeypatch)
    window = _Window()
    position._place(window, shared)

    shared.placing = True
    mac.frame = [1200, 0, 600, 800]
    position._remember(window, shared)
    shared.placing = False
    shared.displays = "laptop-only"  # the displays changed since it was placed
    position._remember(window, shared)
    assert settings.frame(DESK) is None


def test_the_floating_chip_puts_it_back_over_the_terminal(monkeypatch, shared):
    settings.keep_frame(DESK, [1200, 0, 600, 800])
    mac = _Mac(monkeypatch)
    monkeypatch.setattr(threading, "Thread", lambda target, args, daemon: _Run(target, args))

    position.stick(_Window(), shared)
    assert settings.frame(DESK) is None and mac.calls[-1] == "cover" and shared.over


class _Run:
    def __init__(self, target, args):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def _window_up(monkeypatch):
    window = _Window()
    window.native, window.show = _Native(True), lambda: None
    monkeypatch.setattr(position.native, "raise_", lambda _w: None)
    return window


def test_summoned_while_up_it_stays_where_it_floats_unless_the_terminal_is_now_under_it(
    monkeypatch, shared
):
    settings.keep_frame(DESK, [1200, 0, 600, 800])
    mac = _Mac(monkeypatch, window_frame=[1200, 0, 600, 800])
    monkeypatch.setattr(position.native, "front_app", lambda: object())
    window = _window_up(monkeypatch)

    position.show(window, shared, "")
    assert "cover" not in mac.calls and not shared.over

    mac.terminal = [1200, 0, 600, 800]  # the terminal was moved under the floating window
    position.show(window, shared, "")
    assert mac.calls[-1] == "cover" and shared.over


def test_summoned_with_itself_in_front_it_keeps_its_terminal_and_stays_up_after_a_jump(
    monkeypatch, shared
):
    settings.keep_frame(DESK, [1200, 0, 600, 800])
    mac = _Mac(monkeypatch, window_frame=[1200, 0, 600, 800])
    monkeypatch.setattr(position.native, "front_app", lambda: None)  # its own process
    window = _window_up(monkeypatch)

    position.show(window, shared, "")
    position.leave(window, shared)
    assert mac.calls == ["focus"]


def test_a_burst_of_screen_notices_moves_the_window_once_and_only_for_new_displays(
    monkeypatch, shared
):
    mac = _Mac(monkeypatch)
    later = []
    monkeypatch.setattr(position.AppHelper, "callLater", lambda _delay, f: later.append(f))
    window = _window_up(monkeypatch)
    position._place(window, shared)

    def burst():
        for _ in range(100):
            position.displays_changed(window, shared)
        for f in later:
            f()

    burst()
    assert mac.calls == ["cover"]  # the same displays: left as it was placed

    monkeypatch.setattr(position.native, "displays", lambda: "laptop-only")
    burst()
    assert mac.calls == ["cover", "cover"]
