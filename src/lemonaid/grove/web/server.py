"""`lemonaid grove serve`: the grove window's page, served to a browser.

The page and its calls into Python are the grove window's (`window/api.py`). What a browser on
another machine can't use is left out: placing the window, and switching a terminal on the server.
A lemon whose front end is a chat room opens its room in the browser instead.
"""

import functools
import http.server
import json
import threading
import time
import urllib.parse
from importlib import resources

from ...config import Config
from ...front_end import chat
from ...inbox import db
from ...log import get_logger
from ..window import api, data, page

_log = get_logger("grove.web")

REFRESH_SECONDS = 3.0
_CALLS = frozenset(name for name in vars(api.Api) if not name.startswith("_"))


def _jump(channel: str) -> str | dict[str, str]:
    """{"open": url} for the browser to open, or why it can't jump."""
    with db.connect() as conn:
        found = db.get_by_channel(conn, channel, unread_only=False)
    if found is None:
        return f"No live lemon on {channel}"

    name = found.name or channel
    if found.switch_source != chat.NAME:
        return f"{name} runs in a terminal; open it from its own machine"

    url = chat.room_url(str(found.metadata.get("session_key") or ""))
    return {"open": url} if url else f"{name} has no chat room to open"


class _WebApi(api.Api):
    def jump(self, channel: str) -> str | dict[str, str]:  # type: ignore[override]
        return _jump(channel)


def html() -> str:
    """The window's page, with the shim that turns its Python calls into requests first."""
    shim = resources.files(__package__).joinpath("shim.js").read_text()
    window_page = page.html()
    at = window_page.index("<script")
    return f"{window_page[:at]}<script>\n{shim}</script>\n{window_page[at:]}"


def _handler(calls: api.Api, body: bytes) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, status: int, content: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, body, "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def _from_the_page(self) -> bool:
            """A call from the served page: JSON, from the page's own origin. A page on another site
            can POST here as a form does, and the call's effect would happen though it can't read
            the answer. A client that sends no Origin is not a browser page."""
            origin = self.headers.get("Origin")
            same = not origin or urllib.parse.urlsplit(origin).netloc == self.headers.get("Host")
            return same and self.headers.get_content_type() == "application/json"

        def do_POST(self) -> None:
            name = self.path.removeprefix("/api/")
            if not self.path.startswith("/api/") or name not in _CALLS:
                self._send(404, b"not found", "text/plain")
                return

            if not self._from_the_page():
                self._send(403, b"only the grove page may call this", "text/plain")
                return

            length = int(self.headers.get("Content-Length") or 0)
            try:
                args = json.loads(self.rfile.read(length) or b"[]")
                result = getattr(calls, name)(*args)
            except (ValueError, TypeError) as error:
                self._send(400, str(error).encode(), "text/plain")
                return

            self._send(200, json.dumps(result).encode(), "application/json")

        def log_message(self, format: str, *args: object) -> None:
            _log.debug(format, *args)

    return Handler


def _reload(shared: api.Shared) -> None:
    try:
        shared.grove = data.load(shared.config)
    except Exception:  # a refresh thread's top: log it and keep the last grove
        _log.exception("can't load the grove")


def _refresher(shared: api.Shared) -> None:
    while True:
        time.sleep(REFRESH_SECONDS)
        _reload(shared)


def serve(config: Config, host: str, port: int) -> None:
    shared = api.Shared(config)
    _reload(shared)
    nothing = lambda: None  # noqa: E731
    calls = _WebApi(
        shared,
        hide=nothing,
        refresh=lambda: threading.Thread(target=_reload, args=(shared,), daemon=True).start(),
        leave=nothing,
        stick=nothing,
        drag=nothing,
    )
    threading.Thread(target=functools.partial(_refresher, shared), daemon=True).start()
    with http.server.ThreadingHTTPServer((host, port), _handler(calls, html().encode())) as server:
        print(
            f"serving the grove at http://{host}:{port}/ with no login: anyone who reaches"
            " this address controls the grove",
            flush=True,
        )
        server.serve_forever()
