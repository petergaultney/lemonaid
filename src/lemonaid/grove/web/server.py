"""`lemonaid grove serve`: the grove window's page, served to a browser.

The page and its calls into Python are the grove window's (`window/api.py`). What a browser on
another machine can't use is left out: placing the window, and switching a terminal on the server.
Jumping to a lemon opens its own page instead (`lemon.py`), except for a browser on the server
itself, which can switch the terminal as the window does. Each page hears when the grove changed
over its own open stream (`changes.py`), where the window has Python push it.
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
from collections import abc

from ...brief import pr
from ...config import Config
from ...inbox import db, pins
from ...log import get_logger
from ...openclaw import gateway
from ..window import api, data, edits
from . import attachments, brief_page, changes, lemon, notes, pages

_log = get_logger("grove.web")

REFRESH_SECONDS = 3.0
_ZIP_ABOVE = 1024  # bytes; a smaller answer goes as it is
_LOOPBACK = frozenset({"127.0.0.1", "::1"})
_MAX_CALL_BYTES = attachments.MAX_BYTES * 4 // 3 + 64 * 1024  # an attachment, as base64 in JSON


class _WebApi(api.Api):
    def __init__(
        self, shared: api.Shared, prs: pr.Lookup, **window: abc.Callable[[], None]
    ) -> None:
        """*prs* answers a PR's state without waiting; *window* is the window `Api`'s callbacks."""
        super().__init__(shared, **window)
        self._prs = prs

    def look(self) -> dict:
        return {**super().look(), "summoned": False}  # a browser's page stays open

    def jump(self, channel: str) -> str | dict[str, str]:  # type: ignore[override]
        with db.connect() as conn:
            found = db.get_by_channel(conn, channel, unread_only=False)
        return {"lemon": channel} if found else f"No live lemon on {channel}"

    def switch(self, channel: str) -> str:
        """The window's jump, which switches the server's terminal."""
        return super().jump(channel)

    def lemon(self, channel: str, width: int = brief_page.WIDTH) -> dict:
        return lemon.view(channel, self._shared.config, self._prs, int(width))

    def talk(self, channel: str) -> dict:
        return lemon.talk(channel)

    def say(self, channel: str, text: str, attached: abc.Sequence[str] = ()) -> str:
        return lemon.say(channel, text, self._shared.config, attached)

    def attach(self, name: str, mime: str, content: str) -> dict | str:
        return attachments.save(name, mime, content)

    def detach(self, found_id: str) -> str:
        return attachments.drop(found_id)

    def vaults(self) -> list[str]:
        return [root.name for root in self._shared.config.brief.vaults]

    def pins(self) -> list[str]:
        """The pinned lemons' channels, in the inbox's order."""
        with db.connect() as conn:
            at = pins.pinned_positions(conn)
        return sorted(at, key=at.__getitem__)

    def _placed(self, channel: str) -> tuple[str, str] | str:
        grove = self._shared.grove
        if grove is None:
            return "the grove is loading"
        return edits.placed(grove, channel) or "the grove doesn't show that lemon"

    def lemon_edit_info(self, action: str, channel: str) -> dict:
        """The window's `edit_info` for a page that knows only the lemon."""
        at = self._placed(channel)
        return {"problem": at} if isinstance(at, str) else self.edit_info(action, *at, channel)

    def lemon_edit(self, action: str, channel: str, answer: str) -> dict:
        """What happened, and whether the lemon is gone from the inbox now, as an archived one is:
        the edits answer a refusal and a change alike in words, and its page has nothing to show."""
        at = self._placed(channel)
        said = at if isinstance(at, str) else self.edit(action, *at, channel, answer)
        with db.connect() as conn:
            row = db.get_by_channel(conn, channel, unread_only=False)
        return {"said": said, "gone": row is None or row.is_archived}


# What a browser may call, named one by one so a method added to the native window isn't served
# by accident. The window's own placing (dismiss, drag, stick, to_terminal) and open_link are the
# browser's to do (shim.js) and aren't here.
_CALLS = frozenset(
    {
        "attach",
        "block_refusal",
        "data",
        "detach",
        "edit",
        "edit_info",
        "jump",
        "keep",
        "lemon",
        "lemon_edit",
        "lemon_edit_info",
        "log",
        "look",
        "pins",
        "plant",
        "reframe",
        "refusal",
        "say",
        "search",
        "settings",
        "stump_drop",
        "stump_refusal",
        "switch",
        "talk",
        "usage",
        "vaults",
    }
)


def _handler(
    calls: api.Api, served: abc.Mapping[str, tuple[bytes, str]], seen: changes.Changes
) -> type[http.server.BaseHTTPRequestHandler]:
    """*served* is each page and icon by its path, with its content type (`pages.served`)."""

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
            path = urllib.parse.urlsplit(self.path).path.strip("/").removesuffix("index.html")
            if path == "api/changes":
                self._stream(lambda write: changes.stream(seen, write, self._gone))
                return

            if path == "api/talk-changes":
                asked = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                mark = functools.partial(lemon.mark, asked.get("channel", [""])[0])
                self._stream(lambda write: changes.watch(mark, write, self._gone))
                return

            if not path and pages.for_phone(self.headers.get("User-Agent", "")):
                self.send_response(302)
                self.send_header("Location", "groups")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            found = served.get(path or "grove")
            if found:
                self._page(*found)
            else:
                self._send(404, b"not found", "text/plain")

        def _client(self) -> str:
            """The browser's address, also behind a proxy on this machine, such as `tailscale
            serve`, which connects from here and names the browser in X-Forwarded-For."""
            peer = self.client_address[0]
            here = peer.startswith("127.") or peer in ("::1", self.server.server_address[0])
            forwarded = self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            return forwarded if here and forwarded else peer

        def _stream(self, run: abc.Callable[[abc.Callable[[bytes], None]], None]) -> None:
            """A stream of server-sent events that *run* writes, if this browser may open one."""
            with seen.admitted(self._client()) as ok:
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
                    run(write)
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
            if length > _MAX_CALL_BYTES:
                self.close_connection = True  # what it sent is left unread
                self._send(413, b"too large", "text/plain")
                return

            sent = self.rfile.read(length)  # even if refused: the connection carries the next call
            name = self.path.removeprefix("/api/")
            if name == "note" and self._from_the_page():
                self._note(sent)
                return

            if not self.path.startswith("/api/") or name not in _CALLS:
                self._send(404, b"not found", "text/plain")
                return

            if not self._from_the_page():
                self._send(403, b"only the grove page may call this", "text/plain")
                return

            if name == "switch" and self.client_address[0] not in _LOOPBACK:
                self._send(
                    403, b"only a browser on this machine can switch its terminal", "text/plain"
                )
                return

            began = time.monotonic()
            try:
                args = json.loads(sent or b"[]")
                result = getattr(calls, name)(*args)
            except (ValueError, TypeError) as error:
                notes.call(name, time.monotonic() - began, str(error), self.client_address[0])
                self._send(400, str(error).encode(), "text/plain")
                return

            notes.call(name, time.monotonic() - began, "", self.client_address[0], args)
            self._send(200, json.dumps(result).encode(), "application/json")

        def _note(self, sent: bytes) -> None:
            try:
                found = json.loads(sent or b"[]") if len(sent) <= 64_000 else []
            except ValueError:
                found = []
            for event in found if isinstance(found, list) else [found]:
                if isinstance(event, dict):
                    notes.write({"kind": "page", **event}, self.client_address[0])
            self._send(204, b"", "text/plain")

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


def serve(config: Config, host: str, port: int, app: str) -> None:
    gateway.hold()
    shared, seen = api.Shared(config), changes.Changes()
    _reload(shared, seen)
    nothing = lambda: None  # noqa: E731
    calls = _WebApi(
        shared,
        pr.Cache(pr.configured(config.brief.pr_state)).get,
        hide=nothing,
        refresh=lambda: threading.Thread(target=_reload, args=(shared, seen), daemon=True).start(),
        leave=nothing,
        stick=nothing,
        drag=nothing,
    )
    threading.Thread(target=functools.partial(_refresher, shared, seen), daemon=True).start()
    with http.server.ThreadingHTTPServer(
        (host, port), _handler(calls, pages.served(config.web, app), seen)
    ) as server:
        print(
            f"serving the grove at http://{host}:{port}/ with no login: anyone who reaches"
            " this address controls the grove",
            flush=True,
        )
        server.serve_forever()
