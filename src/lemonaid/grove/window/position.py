"""Where the grove window goes on screen, and whether it stays up after a jump. Over the terminal
(see `placement`), it covers the terminal on each summon and hides once a lemon is chosen; moved
away, it opens where it was left with the same displays and stays up, giving the terminal the focus.

AppKit calls go to the main thread through `AppHelper.callAfter`. `window.run_js` waits for the
page on the main thread, so it is only ever called from another thread.
"""

import threading

import webview
from PyObjCTools import AppHelper

from ...log import get_logger
from . import api, native, placement, settings

_log = get_logger("grove.window")


def _share(shared: api.Shared) -> float:
    return shared.config.tui.grove_window_cover_share


def _say_placement(window: webview.Window, shared: api.Shared) -> None:
    """Tell the page whether the window is over the terminal; `run_js` from a thread of its own,
    since this is called on the main thread."""
    js = f"window.setPlacement && window.setPlacement({'true' if shared.over else 'false'})"
    threading.Thread(target=window.run_js, args=(js,), daemon=True).start()


def _remember(window: webview.Window, shared: api.Shared) -> None:
    """Keep where the window was left, for the displays it was placed with; left over the
    terminal, it goes back over it with them. A move while the displays change is macOS's, not
    yours, so it isn't kept."""
    now = native.frame_of(window.native)
    if shared.placing or now == shared.placed or native.displays() != shared.displays:
        return

    terminal = native.terminal_frame(shared.terminal)
    shared.over, shared.placed = placement.over_terminal(now, terminal, _share(shared)), now
    if shared.over:
        settings.forget_frame(shared.displays)
    else:
        settings.keep_frame(shared.displays, now)
    _log.info(
        "left %s at %s with %s",
        "over the terminal" if shared.over else "away",
        now,
        shared.displays,
    )
    _say_placement(window, shared)


def moved(window: webview.Window, shared: api.Shared) -> None:
    """A drag moves the window many times; only where it rests is kept."""
    shared.moves += 1
    seen = shared.moves
    AppHelper.callLater(0.4, lambda: seen == shared.moves and _remember(window, shared))


def _place(window: webview.Window, shared: api.Shared) -> str:
    """Where it was left with these displays, unless that's over the terminal: then over the
    terminal's window, as it is now. Says where."""
    shared.placing, shared.displays = True, native.displays()
    try:
        kept, terminal = settings.frame(shared.displays), native.terminal_frame(shared.terminal)
        shared.over = not kept or placement.over_terminal(kept, terminal, _share(shared))
        if shared.over:
            where = native.cover(window.native, shared.terminal)
        else:
            native.put(window.native, kept)
            where = f"where it was left with these displays, {kept}"
        shared.placed = native.frame_of(window.native)
        return where
    finally:
        shared.placing = False


def hide(window: webview.Window, shared: api.Shared) -> None:
    # Hidden first: the page then goes back to the whole grove out of sight.
    AppHelper.callAfter(native.hand_back, window.native, shared.terminal)
    window.run_js("window.setShown && window.setShown(false)")


def leave(window: webview.Window, shared: api.Shared) -> None:
    """Back to the terminal, after a jump or from the summon key: hidden over it, otherwise left up
    with the terminal given the focus."""
    measured, over = threading.Event(), []

    def measure() -> None:
        here, terminal = native.frame_of(window.native), native.terminal_frame(shared.terminal)
        over.append(placement.over_terminal(here, terminal, _share(shared)))
        _log.info(
            "%s: at %s, the terminal's window at %s",
            "hidden" if over[0] else "stays up, giving the terminal the focus",
            here,
            terminal,
        )
        measured.set()

    AppHelper.callAfter(measure)
    measured.wait(2)
    if not over or over[0]:
        hide(window, shared)
    else:
        AppHelper.callAfter(native.focus, shared.terminal)


def drag(window: webview.Window) -> None:
    AppHelper.callAfter(native.drag, window.native)


def stick(window: webview.Window, shared: api.Shared) -> None:
    def stick() -> None:
        settings.forget_frame(native.displays())
        _log.info("back over the terminal: %s", _place(window, shared))
        _say_placement(window, shared)

    AppHelper.callAfter(stick)


def _screens_rested(window: webview.Window, shared: api.Shared) -> None:
    if not window.native.isVisible():
        return

    if native.displays() == shared.displays:
        _log.info("screens changed with the same displays; left where it is")
        return

    _log.info("displays changed; placed %s", _place(window, shared))
    _say_placement(window, shared)


def displays_changed(window: webview.Window, shared: api.Shared) -> None:
    """macOS says the screens changed in bursts of a hundred a second, and also when the displays
    are the same ones as before; only a new set of displays, once the burst rests, moves the window."""
    shared.screen_notices += 1
    seen = shared.screen_notices
    AppHelper.callLater(
        0.5, lambda: seen == shared.screen_notices and _screens_rested(window, shared)
    )


def show(window: webview.Window, shared: api.Shared, client: str) -> None:
    shared.client = client
    placed = threading.Event()

    def place() -> None:
        shared.terminal = native.front_app() or shared.terminal
        terminal = native.terminal_frame(shared.terminal)
        here = native.frame_of(window.native)
        floating = window.native.isVisible() and not placement.over_terminal(
            here, terminal, _share(shared)
        )  # measured against the terminal just summoned from, which may be under it now
        if floating:
            shared.over = False
        else:
            _log.info("placed %s", _place(window, shared))
        placed.set()

    # The terminal is whatever is in front before the window is: `window.show()` queues its own
    # activation. The window takes its frame while still hidden, so it never appears elsewhere first.
    AppHelper.callAfter(place)
    placed.wait(2)
    window.show()
    AppHelper.callAfter(native.raise_, window.native)
    window.run_js("window.setShown && window.setShown(true)")
    window.run_js(
        f"window.setPlacement && window.setPlacement({'true' if shared.over else 'false'})"
    )
    _log.info("shown over client %s", client or "(none)")
