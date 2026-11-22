"""The grove window's process: the window, hidden between uses and shown when its socket asks
(where it goes is `position`'s), and the grove it reloads every few seconds.

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
from . import api, control, data, native, page, position

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


def _serve(window: webview.Window, shared: api.Shared) -> None:
    path = control.socket_path()
    with contextlib.suppress(FileNotFoundError):
        path.unlink()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            control.dispatch(
                self.rfile.readline().decode(),
                show=lambda client: position.show(window, shared, client),
                hide=lambda: position.hide(window, shared),
            )

    with socketserver.ThreadingUnixStreamServer(str(path), Handler) as server:
        server.serve_forever()


def run(config: Config) -> None:
    shared, window_ref = api.Shared(config), []
    page_api = api.Api(
        shared,
        hide=lambda: position.hide(window_ref[0], shared),
        refresh=lambda: threading.Thread(
            target=_refresh, args=(window_ref[0], shared), daemon=True
        ).start(),
        leave=lambda: position.leave(window_ref[0], shared),
        stick=lambda: position.stick(window_ref[0], shared),
        drag=lambda: position.drag(window_ref[0]),
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
        AppHelper.callAfter(native.on_moved, window.native, lambda: position.moved(window, shared))
        AppHelper.callAfter(
            native.on_displays_changed, lambda: position.displays_changed(window, shared)
        )
        threading.Thread(target=_serve, args=(window, shared), daemon=True).start()
        _log.info("listening on %s", control.socket_path())

    # The first load runs while WebKit starts; it hands the page the grove once the page is loaded.
    threading.Thread(target=_refresher, args=(window, shared), daemon=True).start()
    # Private mode, pywebview's default, wipes the WebKit store every unbundled Python app shares, at
    # each start; the page keeps nothing there (window/settings.py keeps its state).
    webview.start(started, private_mode=False)
