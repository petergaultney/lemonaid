"""One running plugin, and the framing every kind of plugin shares.

The plugin starts once, says hello with one line naming its kind and version, and serves
requests on stdin, one at a time:

    -> <header>                    such as `threads /notes/plan.md`
    -> <field> <value>             any number of them
    -> text <n>                    then exactly n bytes, UTF-8
    <- ok <n>                      then exactly n bytes of the result, UTF-8
    <- error <message>

Any other line the plugin writes, at any time, is a notice: `on_notice` gets it, and a
pending request keeps waiting for its answer. Closing stdin asks the plugin to exit.
"""

import os
import selectors
import subprocess
import time
from collections import abc

from .command import Plugin

Notice = abc.Callable[[str], None]


class Failed(Exception):
    pass


class _Reader:
    """Reads lines and counted bytes from a pipe, giving up at a deadline."""

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._buffer = b""
        self._selector = selectors.DefaultSelector()
        self._selector.register(fd, selectors.EVENT_READ)

    def _fill(self, deadline: float) -> bool:
        """False when nothing came by *deadline*."""
        if not self._selector.select(max(0.0, deadline - time.monotonic())):
            return False

        chunk = os.read(self._fd, 65536)
        if not chunk:
            raise Failed("exited")

        self._buffer += chunk
        return True

    def line(self, deadline: float) -> bytes | None:
        """The next line, or None when none is complete by *deadline*."""
        while b"\n" not in self._buffer:
            if not self._fill(deadline):
                return None
        found, _, self._buffer = self._buffer.partition(b"\n")
        return found

    def exactly(self, n: int, deadline: float) -> bytes:
        while len(self._buffer) < n:
            if not self._fill(deadline):
                raise Failed("timed out")
        found, self._buffer = self._buffer[:n], self._buffer[n:]
        return found

    def close(self) -> None:
        self._selector.close()


def _write_all(fd: int, data: bytes, deadline: float) -> None:
    """Write *data* to a non-blocking pipe, failing at *deadline*: a plugin that stops
    reading must not hold its caller once the pipe fills."""
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_WRITE)
        view = memoryview(data)
        while view:
            if not selector.select(max(0.0, deadline - time.monotonic())):
                raise Failed("timed out writing its request")

            try:
                view = view[os.write(fd, view) :]
            except BlockingIOError:
                continue
            except OSError as e:
                raise Failed(f"exited ({e})") from e


def _request(header: str, fields: abc.Sequence[tuple[str, str]], text: str) -> bytes:
    lines = [header, *(f"{name} {value}" for name, value in fields)]
    if any("\n" in line for line in lines):
        raise Failed("a request line can't hold a line break")

    body = text.encode()
    return "".join(f"{line}\n" for line in [*lines, f"text {len(body)}"]).encode() + body


class Running:
    def __init__(
        self,
        plugin: Plugin,
        hello: bytes,
        timeout: float,
        on_notice: Notice | None = None,
        env: abc.Mapping[str, str] | None = None,
    ) -> None:
        self.plugin = plugin
        self._timeout = timeout
        self._on_notice = on_notice
        try:
            self._proc = subprocess.Popen(
                plugin.argv,
                bufsize=0,  # unbuffered, so nothing waits in a buffer to be flushed
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,
                env={**os.environ, **env} if env is not None else None,
            )
        except OSError as e:
            raise Failed(str(e)) from e

        assert self._proc.stdin is not None and self._proc.stdout is not None
        os.set_blocking(self._proc.stdin.fileno(), False)
        self._reader = _Reader(self._proc.stdout.fileno())
        try:
            said = self._reader.line(time.monotonic() + timeout)
        except Failed:
            self.close()
            raise

        if said is None or said.strip() != hello:
            self.close()
            raise Failed(
                "timed out" if said is None else f"said {said[:80]!r}, not {hello.decode()!r}"
            )

    def _answer_line(self, deadline: float) -> str:
        """The next `ok` or `error` line, passing notices on as they come."""
        while (line := self._reader.line(deadline)) is not None:
            decoded = line.decode(errors="replace")
            if decoded.partition(" ")[0] in ("ok", "error"):
                return decoded

            if self._on_notice:
                self._on_notice(decoded)
        raise Failed("timed out")

    def ask(self, header: str, fields: abc.Sequence[tuple[str, str]], text: str) -> str:
        """The result, or Failed; after a Failed, close this process and start another."""
        assert self._proc.stdin is not None
        deadline = time.monotonic() + self._timeout
        _write_all(self._proc.stdin.fileno(), _request(header, fields, text), deadline)

        status, _, rest = self._answer_line(deadline).partition(" ")
        if status == "error":
            raise Failed(rest or "error")

        if not rest.isdigit():
            raise Failed(f"answered ok {rest}"[:120])

        try:
            return self._reader.exactly(int(rest), deadline).decode()
        except UnicodeDecodeError as e:
            raise Failed("answered with text that is not UTF-8") from e

    def read_notices(self, timeout: float) -> None:
        """Pass on the notices that arrive within *timeout*, between requests."""
        deadline = time.monotonic() + timeout
        while (line := self._reader.line(deadline)) is not None:
            if self._on_notice:
                self._on_notice(line.decode(errors="replace"))

    def close(self) -> None:
        """Closing stdin asks the plugin to exit; one that doesn't within a second is killed."""
        self._reader.close()
        for pipe in (self._proc.stdin, self._proc.stdout):
            try:
                if pipe:
                    pipe.close()
            except OSError:
                pass  # unbuffered, so closing flushes nothing; a broken pipe needs no more
        try:
            self._proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
