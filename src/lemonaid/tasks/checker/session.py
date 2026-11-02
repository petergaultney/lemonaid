"""One long-running checker process, asked over the serve protocol (`stream.py`).

The process starts on the first request and again after it exits or misses a deadline,
when every request still waiting on it fails. Requests may be asked from several threads,
and their answers return in whatever order the checker gives them. A writer thread feeds
the process, so a checker that stops reading can't block a caller past its deadline.
"""

import concurrent.futures
import itertools
import queue
import subprocess
import threading
import typing as ty
from collections import abc

from ...log import get_logger
from . import protocol, stream

_log = get_logger("tasks.checker.session")

Ask = abc.Callable[[str, str], str]  # (operation, input) -> output


class Failed(subprocess.SubprocessError):
    pass


class Session:
    """The process is an external resource, so it is kept in an object."""

    def __init__(self, argv: abc.Sequence[str], timeout: float) -> None:
        self._argv, self._timeout = [*argv, "serve"], timeout
        self._process: subprocess.Popen[str] | None = None
        self._outbox: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        self._waiting: dict[
            str, tuple[subprocess.Popen[str], concurrent.futures.Future[str]]
        ] = {}  # by request ID, with the process it was sent to
        self._lock = threading.Lock()
        self._ids = itertools.count()

    def _read(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        why = "the checker exited"
        try:
            for frame in stream.frames(process.stdout):
                with self._lock:
                    sent = self._waiting.get(frame.request_id)
                    if sent is None or sent[0] is not process:
                        continue

                    del self._waiting[frame.request_id]
                waiting = sent[1]

                if frame.kind == "failed":
                    waiting.set_exception(Failed(frame.detail))
                else:
                    waiting.set_result(frame.body)
        except protocol.ProtocolError as error:
            why = f"the checker broke the serve protocol: {error}"
            _log.warning("%s", why)
            process.kill()
        with self._lock:
            if self._process is process:
                self._process = None
            left = [w for p, w in self._waiting.values() if p is process]
            self._waiting = {r: s for r, s in self._waiting.items() if s[0] is not process}
        for waiting in left:
            waiting.set_exception(Failed(why))

    @staticmethod
    def _write(process: subprocess.Popen[str], outbox: queue.SimpleQueue[str | None]) -> None:
        """Send each queued request until None, then close the process's input."""
        assert process.stdin is not None
        try:
            while (frame := outbox.get()) is not None:
                process.stdin.write(frame)
                process.stdin.flush()
            process.stdin.close()
        except OSError:
            process.kill()  # its reader fails whatever is still waiting

    def _running(self) -> queue.SimpleQueue[str | None]:
        if self._process is None or self._process.poll() is not None:
            self._process = subprocess.Popen(
                self._argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1
            )
            self._outbox = queue.SimpleQueue()
            for target, args in (
                (self._read, (self._process,)),
                (self._write, (self._process, self._outbox)),
            ):
                threading.Thread(target=target, args=args, name="task-checker", daemon=True).start()
        return self._outbox

    def ask(self, operation: str, text: str) -> str:
        """The checker's output within the timeout, sending included; raises Failed, or
        OSError if it can't be started."""
        answer: concurrent.futures.Future[str] = concurrent.futures.Future()
        with self._lock:
            outbox = self._running()
            request_id = str(next(self._ids))
            assert self._process is not None
            self._waiting[request_id] = (self._process, answer)
            outbox.put(stream.request(request_id, operation, text))
        try:
            return answer.result(timeout=self._timeout)
        except concurrent.futures.TimeoutError:
            self.close(hung=True)
            raise Failed(f"the checker gave no answer in {self._timeout:g} s") from None

    def close(self, hung: bool = False) -> None:
        """Stop the process: once its writer has sent what's queued and closed its input, or
        with *hung*, by killing it."""
        with self._lock:
            process, self._process = self._process, None
            self._outbox.put(None)
        if process is None:
            return

        try:
            process.wait(timeout=0 if hung else 5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def __enter__(self) -> ty.Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
