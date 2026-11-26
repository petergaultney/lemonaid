"""`lemonaid grove serve`: the grove window's page, served to a browser.

The page and its calls into Python are the grove window's (`window/api.py`). What a browser on
another machine can't use is left out: placing the window, and switching a terminal on the server.
A lemon whose front end is a chat room opens its room in the browser instead. Each page hears
when the grove changed over its own open stream (`changes.py`), where the window has Python push it.
"""

import functools
import gzip
import hashlib
import http.server
import json
import select
import socket
import threading
import time
import urllib.parse
from importlib import resources

from ...config import Config
from ...front_end import chat
from ...inbox import db
from ...log import get_logger
from ..window import api, data, page
from . import changes

_log = get_logger("grove.web")

REFRESH_SECONDS = 3.0
_ZIP_ABOVE = 1024  # bytes; a smaller answer goes as it is
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


def _handler(
    calls: api.Api, body: bytes, seen: changes.Changes
) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # a page's calls share one connection, not one each

        def _send(
            self, status: int, content: bytes, kind: str, cache: str = "no-store", tag: str = ""
        ) -> None:
            zipped = len(content) > _ZIP_ABOVE and "gzip" in self.headers.get("Accept-Encoding", "")
            sent = gzip.compress(content, compresslevel=5) if zipped else content
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(sent)))
            self.send_header("Cache-Control", cache)
            self.send_header("Vary", "Accept-Encoding")
            if zipped:
                self.send_header("Content-Encoding", "gzip")
            if tag:
                self.send_header("ETag", tag)
            self.end_headers()
            self.wfile.write(sent)

        def _page(self, content: bytes, kind: str) -> None:
            """A page the browser keeps, and fetches again only once it has changed."""
            tag = f'"{hashlib.blake2b(content, digest_size=8).hexdigest()}"'
            if self.headers.get("If-None-Match") == tag:
                self.send_response(304)
                self.send_header("ETag", tag)
                self.end_headers()
                return

            self._send(200, content, kind, cache="no-cache", tag=tag)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._page(body, "text/html; charset=utf-8")
            elif self.path == "/api/changes":
                self._changes()
            else:
                self._send(404, b"not found", "text/plain")

        def _changes(self) -> None:
            with seen.admitted(self.client_address[0]) as ok:
                if not ok:
                    self._send(204, b"", "text/plain")  # EventSource stops on 204; the page polls
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.close_connection = True  # a stream ends only with its connection

                def write(event: bytes) -> None:
                    self.wfile.write(event)
                    self.wfile.flush()

                try:
                    changes.stream(seen, write, self._gone)
                except (BrokenPipeError, ConnectionResetError):
                    _log.debug("a page closed its stream of changes")

        def _gone(self) -> bool:
            """Whether the page closed its end of a stream: it sends nothing after asking, so
            anything to read means it hung up."""
            if not select.select([self.connection], [], [], 0)[0]:
                return False

            try:
                return not self.connection.recv(1, socket.MSG_PEEK)
            except OSError:
                return True

        def _from_the_page(self) -> bool:
            """A call from the served page: JSON, from the page's own origin. A page on another site
            can POST here as a form does, and the call's effect would happen though it can't read
            the answer. A client that sends no Origin is not a browser page."""
            origin = self.headers.get("Origin")
            same = not origin or urllib.parse.urlsplit(origin).netloc == self.headers.get("Host")
            return same and self.headers.get_content_type() == "application/json"

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            sent = self.rfile.read(length)  # even if refused: the connection carries the next call
            name = self.path.removeprefix("/api/")
            if not self.path.startswith("/api/") or name not in _CALLS:
                self._send(404, b"not found", "text/plain")
                return

            if not self._from_the_page():
                self._send(403, b"only the grove page may call this", "text/plain")
                return

            try:
                args = json.loads(sent or b"[]")
                result = getattr(calls, name)(*args)
            except (ValueError, TypeError) as error:
                self._send(400, str(error).encode(), "text/plain")
                return

            self._send(200, json.dumps(result).encode(), "application/json")

        def log_message(self, format: str, *args: object) -> None:
            _log.debug(format, *args)

    return Handler


def _reload(shared: api.Shared, seen: changes.Changes) -> None:
    try:
        shared.grove = data.load(shared.config)
        seen.saw(data.shown(shared.grove))
    except Exception:  # a refresh thread's top: log it and keep the last grove
        _log.exception("can't load the grove")


def _refresher(shared: api.Shared, seen: changes.Changes) -> None:
    while True:
        time.sleep(REFRESH_SECONDS)
        _reload(shared, seen)


def serve(config: Config, host: str, port: int) -> None:
    shared, seen = api.Shared(config), changes.Changes()
    _reload(shared, seen)
    nothing = lambda: None  # noqa: E731
    calls = _WebApi(
        shared,
        hide=nothing,
        refresh=lambda: threading.Thread(target=_reload, args=(shared, seen), daemon=True).start(),
        leave=nothing,
        stick=nothing,
        drag=nothing,
    )
    threading.Thread(target=functools.partial(_refresher, shared, seen), daemon=True).start()
    with http.server.ThreadingHTTPServer(
        (host, port), _handler(calls, html().encode(), seen)
    ) as server:
        print(
            f"serving the grove at http://{host}:{port}/ with no login: anyone who reaches"
            " this address controls the grove",
            flush=True,
        )
        server.serve_forever()
