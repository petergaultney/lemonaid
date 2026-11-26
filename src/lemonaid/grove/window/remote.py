"""`lemonaid grove window remote`: another machine's web grove (`grove serve`) in this machine's
grove window, see-through as the window is.

The page is the window's own. Its calls about the grove go to the server, and it redraws when the
server's stream of changes says the grove changed. How it looks (this machine's config), links,
and moving or hiding the window stay here. A lemon's page opens in a window of its own over the
grove, and going back closes it, leaving the grove as it was.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from collections import abc

import webview

from ...config import Config
from ...log import get_logger
from . import api, page, position

_log = get_logger("grove.remote")

_TIMEOUT_SECONDS = 30
_STREAM_SECONDS = 60.0  # longer than the server's heartbeat, so a quiet stream isn't a dead one
_RETRY_SECONDS = 3.0
_PROBLEM = object()  # a call that answers with a problem to show, here that the server is away
_FORWARDED: dict[str, object] = {  # each call the server answers, and what stands in without it
    "data": None,
    "search": [],
    "usage": [],
    "settings": {},
    "keep": None,
    "edit_info": {},
    "edit": _PROBLEM,
    "refusal": _PROBLEM,
    "plant": _PROBLEM,
    "block_refusal": _PROBLEM,
    "reframe": _PROBLEM,
    "stump_refusal": _PROBLEM,
    "stump_drop": _PROBLEM,
}


def _call(base: str, name: str, args: abc.Sequence[object]) -> object:
    request = urllib.request.Request(
        f"{base}api/{name}",
        data=json.dumps(list(args)).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as answer:
        return json.loads(answer.read())


def _forwarder(name: str, without: object) -> abc.Callable[..., object]:
    def forward(self: "RemoteApi", *args: object) -> object:
        try:
            return _call(self.base, name, args)
        except (OSError, ValueError) as error:
            _log.warning("%s: %s", name, error)
            return f"the grove at {self.base} didn't answer" if without is _PROBLEM else without

    return forward


class RemoteApi:
    """The page's calls: the grove's go to the server at *base*; the window's go to *local*.
    *show* loads a page of the server's into the window, and *home* the window's own page."""

    def __init__(
        self,
        base: str,
        local: api.Api,
        show: abc.Callable[[str], None],
        home: abc.Callable[[], None],
    ) -> None:
        self.base, self._local, self._show, self._home = base, local, show, home

    def jump(self, channel: str) -> str:
        """Show the lemon's page in the window, or open its chat room in the browser."""
        try:
            answer = _call(self.base, "jump", [channel])
        except (OSError, ValueError) as error:
            return f"the grove at {self.base} didn't answer: {error}"

        if isinstance(answer, dict) and answer.get("lemon"):
            self._show(f"{self.base}lemon?{urllib.parse.urlencode({'channel': channel})}")
            return ""

        if isinstance(answer, dict) and answer.get("open"):
            self._local.open_link(str(answer["open"]))
            return ""

        return str(answer)

    def home(self) -> None:
        """Back to the grove from a lemon's page."""
        self._home()

    def look(self) -> dict:
        return {**self._local.look(), "summoned": False}  # this window stays open

    def open_link(self, url: str) -> None:
        self._local.open_link(url)

    def log(self, line: str) -> None:
        self._local.log(line)

    def dismiss(self) -> None:
        self._local.dismiss()

    def to_terminal(self) -> None:
        self._local.to_terminal()

    def drag(self) -> None:
        self._local.drag()

    def stick(self) -> None:
        """There is no terminal here to put the window over."""


for _name, _without in _FORWARDED.items():
    setattr(RemoteApi, _name, _forwarder(_name, _without))


def _listen(base: str, redraw: abc.Callable[[], None]) -> None:
    """Redraw on each change the server reports, and on each reconnection for what changed while
    the stream was down; a server that turns the stream away is asked again every few seconds."""
    while True:
        try:
            with urllib.request.urlopen(f"{base}api/changes", timeout=_STREAM_SECONDS) as stream:
                redraw()
                for line in stream:
                    if line.startswith(b"data:"):
                        redraw()
        except OSError as error:
            _log.info("change stream from %s: %s", base, error)
        time.sleep(_RETRY_SECONDS)


def _lemons(calls: list["RemoteApi"]) -> tuple[abc.Callable[[str], None], abc.Callable[[], None]]:
    """Show a lemon's page in a window of its own over the grove, and close it again, so going
    back leaves the grove's window as it was."""
    shown: list[webview.Window] = []

    def show(url: str) -> None:
        if shown:
            shown[0].load_url(url)
            shown[0].show()
            return

        lemon = webview.create_window("lemon", url, js_api=calls[0], width=1100, height=760)
        lemon.events.closed += shown.clear
        shown.append(lemon)

    def home() -> None:
        if shown:
            shown.pop().destroy()

    return show, home


def run(config: Config, url: str) -> None:
    base = url if url.endswith("/") else f"{url}/"
    window_ref: list[webview.Window] = []
    local = api.Api(
        api.Shared(config),
        hide=lambda: window_ref[0].minimize(),
        refresh=lambda: None,  # the server reloads after each edit and says so
        leave=lambda: window_ref[0].minimize(),
        stick=lambda: None,
        drag=lambda: position.drag(window_ref[0]),
    )
    calls_ref: list[RemoteApi] = []
    show, home = _lemons(calls_ref)
    calls_ref.append(RemoteApi(base, local, show=show, home=home))
    window = webview.create_window(
        f"lemon grove at {urllib.parse.urlsplit(base).hostname}",
        html=page.html(),
        js_api=calls_ref[0],
        frameless=True,
        easy_drag=False,
        width=1200,
        height=800,
        transparent=True,
    )
    window_ref.append(window)

    def redraw() -> None:
        window.run_js("window.groveData && window.groveData()")

    threading.Thread(target=_listen, args=(base, redraw), daemon=True).start()
    webview.start(private_mode=False)
