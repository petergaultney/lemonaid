"""The grove window: hidden between uses, shown over the terminal when its socket asks, and
hidden again once a lemon is chosen.

AppKit calls go to the main thread through `AppHelper.callAfter`. `window.run_js` waits for the
page on the main thread, so it is only ever called from another thread.
"""

import contextlib
import socketserver
import threading
import time

import webview
from PyObjCTools import AppHelper

from ...config import Config
from ...log import get_logger
from . import api, control, data, native, page

_log = get_logger("grove.window")
REFRESH_SECONDS = 3.0


def _refresh(window: webview.Window, shared: api.Shared) -> None:
    try:
        shared.grove = data.load(shared.config)
    except Exception:  # a refresh thread's top: log it and keep the last grove
        _log.exception("can't load the grove")
        return

    window.run_js("window.groveData && window.groveData()")


def _refresher(window: webview.Window, shared: api.Shared) -> None:
    while True:
        _refresh(window, shared)
        time.sleep(REFRESH_SECONDS)


def _hide(window: webview.Window, shared: api.Shared) -> None:
    # Hidden first: the page then goes back to the whole grove out of sight.
    AppHelper.callAfter(native.hand_back, window.native, shared.terminal)
    window.run_js("window.setShown && window.setShown(false)")


def _show(window: webview.Window, shared: api.Shared, client: str) -> None:
    shared.client = client
    placed = threading.Event()

    def place() -> None:
        shared.terminal = native.front_app()
        _log.info("covering %s", native.cover(window.native, shared.terminal))
        placed.set()

    # The terminal is whatever is in front before the window is: `window.show()` queues its own
    # activation. The window takes the terminal's frame while still hidden, so it never appears
    # at another size first.
    AppHelper.callAfter(place)
    placed.wait(2)
    window.show()
    AppHelper.callAfter(native.raise_, window.native)
    window.run_js("window.setShown && window.setShown(true)")
    _log.info("shown over client %s", client or "(none)")


def _serve(window: webview.Window, shared: api.Shared) -> None:
    path = control.socket_path()
    with contextlib.suppress(FileNotFoundError):
        path.unlink()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            control.dispatch(
                self.rfile.readline().decode(),
                show=lambda client: _show(window, shared, client),
                hide=lambda: _hide(window, shared),
            )

    with socketserver.ThreadingUnixStreamServer(str(path), Handler) as server:
        server.serve_forever()


def run(config: Config) -> None:
    shared, window_ref = api.Shared(config), []
    page_api = api.Api(
        shared,
        hide=lambda: _hide(window_ref[0], shared),
        refresh=lambda: threading.Thread(
            target=_refresh, args=(window_ref[0], shared), daemon=True
        ).start(),
    )
    window = webview.create_window(
        "lemon grove",
        html=page.html(),
        js_api=page_api,
        frameless=True,
        easy_drag=False,
        width=1200,
        height=800,
        hidden=True,
        transparent=True,
    )
    window_ref.append(window)

    def started() -> None:
        AppHelper.callAfter(native.accessory)
        threading.Thread(target=_refresher, args=(window, shared), daemon=True).start()
        threading.Thread(target=_serve, args=(window, shared), daemon=True).start()
        _log.info("listening on %s", control.socket_path())

    # Private mode, pywebview's default, wipes the WebKit store every unbundled Python app shares, at
    # each start; the page keeps nothing there (window/settings.py keeps its state).
    webview.start(started, private_mode=False)
