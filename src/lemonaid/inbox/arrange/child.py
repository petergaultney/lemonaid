"""The arranger process `lma` keeps running: one JSON line in per snapshot, one out per answer.

A snapshot is sent only when it differs from the last one sent, or a minute
after it, so a tick where nothing changed costs one encode. The tick waits
briefly for the answer and otherwise draws the newest one it has. It never
waits on the pipe: a thread writes each snapshot, and a newer one replaces a
snapshot it hasn't written yet.
"""

import json
import os
import queue
import shlex
import subprocess
import threading
import time
from collections import abc
from typing import IO, Any

from ...log import get_logger

_log = get_logger("arrange")
_MAX_BACKOFF = 60.0


def parse_command(command: str) -> list[str]:
    """`[inbox] arrange`'s words, with a leading `~` in each expanded."""
    return [os.path.expanduser(word) for word in shlex.split(command)]


def _pump(stream: abc.Iterable[str], put: abc.Callable[[str], None]) -> None:
    for line in stream:
        put(line)


class _Outbox:
    """The one snapshot waiting to be written to a process, and the thread that writes it."""

    def __init__(self, stdin: IO[str]) -> None:
        self._stdin = stdin
        self._line: str | None = None
        self._closed = False
        self._ready = threading.Condition()
        threading.Thread(target=self._write, daemon=True).start()

    def put(self, line: str) -> bool:
        """Whether *line* adds an answer to wait for, rather than replacing an unwritten line."""
        with self._ready:
            replaced = self._line is not None
            self._line = line
            self._ready.notify()
        return not replaced

    def close(self) -> None:
        with self._ready:
            self._closed = True
            self._ready.notify()

    def _write(self) -> None:
        while True:
            with self._ready:
                while self._line is None and not self._closed:
                    self._ready.wait()
                if self._closed:
                    return

                line, self._line = self._line, None
            try:
                self._stdin.write(line)
                self._stdin.flush()
            except (OSError, ValueError) as e:  # the process is gone; the tick reports how
                _log.info("can't send: %s", e)
                return


class Arranger:
    """The arranger process, restarted with backoff whenever it fails.

    `error` says what went wrong last, in a few words for the status line, and
    is "" while the arranger is answering.
    """

    def __init__(
        self,
        command: abc.Sequence[str],
        *,
        budget: float = 0.05,
        timeout: float = 2.0,
        resend: float = 60.0,
        clock: abc.Callable[[], float] = time.monotonic,
    ) -> None:
        self._command = list(command)
        self._budget = budget
        self._timeout = timeout
        self._resend = resend
        self._clock = clock
        self._proc: subprocess.Popen[str] | None = None
        self._outbox: _Outbox | None = None
        self._lines: queue.Queue[tuple[subprocess.Popen[str], str]] = queue.Queue()
        self._stderr = ""
        self._stderr_pump: threading.Thread | None = None
        self._sent_body = ""
        self._sent_at = 0.0
        self._pending = 0
        self._pending_since = 0.0
        self._restart_at = 0.0
        self._backoff = 1.0
        self.latest: Any = None
        self.error = ""

    def _fail(self, error: str) -> None:
        _log.warning("%s: %s", " ".join(self._command), error)
        self.error = error
        self.latest = None
        self.close()
        self._restart_at = self._clock() + self._backoff
        self._backoff = min(self._backoff * 2, _MAX_BACKOFF)

    def _start(self) -> None:
        try:
            proc = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as e:
            self._fail(f"can't start: {e}")
            return

        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        self._proc = proc
        self._outbox = _Outbox(proc.stdin)
        self._stderr = ""
        self._sent_body = ""
        self._pending = 0
        threading.Thread(
            target=_pump,
            args=(proc.stdout, lambda line: self._lines.put((proc, line))),
            daemon=True,
        ).start()
        self._stderr_pump = threading.Thread(
            target=_pump, args=(proc.stderr, self._log_stderr), daemon=True
        )
        self._stderr_pump.start()

    def _log_stderr(self, line: str) -> None:
        _log.info("stderr: %s", line.rstrip())
        if line.strip():
            self._stderr = line.strip()

    def _take(self, proc: subprocess.Popen[str], line: str) -> None:
        if proc is not self._proc:
            return  # from a process already given up on

        self._pending = max(0, self._pending - 1)
        self._pending_since = self._clock()
        try:
            self.latest = json.loads(line)
        except json.JSONDecodeError as e:
            self._fail(f"answer isn't JSON ({e.msg}): {line.strip()[:60]}")
            return

        self.error = ""
        self._backoff = 1.0

    def _drain(self, wait: float = 0.0) -> None:
        try:
            self._take(*(self._lines.get(timeout=wait) if wait else self._lines.get_nowait()))
            while True:
                self._take(*self._lines.get_nowait())
        except queue.Empty:
            pass

    def _send(self, body: str, now: float) -> None:
        assert self._outbox is not None
        if self._outbox.put(f'{body[:-1]}, "now": {now}}}\n'):
            if not self._pending:
                self._pending_since = self._clock()
            self._pending += 1
        self._sent_body = body
        self._sent_at = self._clock()

    def answer(self, snapshot: abc.Mapping[str, Any], now: float) -> Any:
        """The newest answer, after sending *snapshot* if it is new; None while there is none."""
        self._drain()
        if self._proc is not None and (code := self._proc.poll()) is not None:
            if self._stderr_pump is not None:
                self._stderr_pump.join(timeout=0.2)  # for its last words
            self._drain()
            self._fail(
                f"exited {code}"
                + (f": {self._stderr}" if self._stderr else "")
                + (" (an arranger keeps reading its input)" if code == 0 else "")
            )
        if (
            self._proc is not None
            and self._pending
            and self._clock() - self._pending_since > self._timeout
        ):
            self._fail(f"no answer in {self._timeout:g}s")
        if self._proc is None and self._clock() >= self._restart_at:
            self._start()
        if self._proc is None:
            return None

        body = json.dumps(snapshot)
        if body != self._sent_body or self._clock() - self._sent_at >= self._resend:
            self._send(body, now)
            self._drain(self._budget)
        return self.latest

    def close(self) -> None:
        if self._outbox is not None:
            self._outbox.close()
            self._outbox = None
        if self._proc is not None:
            self._proc.kill()
            self._proc = None
