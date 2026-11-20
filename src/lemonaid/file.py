"""Reading and writing text files that someone may have open in an editor."""

import contextlib
import fcntl
import hashlib
import os
import tempfile
import time
import typing as ty
from collections import abc
from pathlib import Path

_LOCK_POLL_SECONDS: ty.Final = 0.05


class Busy(Exception):
    """Another lemonaid process held the file's lock for the whole wait."""


def _lock_path(target: Path) -> Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    digest = hashlib.sha1(str(target).encode()).hexdigest()[:16]
    return Path(state).expanduser() / "file-locks" / f"{digest}.lock"


@contextlib.contextmanager
def locked(path: Path, *, wait_seconds: float = 5.0) -> abc.Iterator[None]:
    """Hold lemonaid's lock on the file *path* names, from reading it through replacing it.

    `replace` alone can't keep two lemonaid writers apart: both can compare before either
    renames, and the second rename drops the first writer's change. Editors don't take this
    lock, so it only orders lemonaid's own writers. It is an `flock` on a file in lemonaid's
    state directory, keyed by the real path, so a crashed holder releases it and nothing
    appears beside the file. Raises `Busy` after *wait_seconds*, such as when the holder is
    suspended.
    """
    lock_path = _lock_path(path.resolve())
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    with lock_path.open("a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Busy(f"another lemonaid process is writing {path}") from None
                time.sleep(_LOCK_POLL_SECONDS)
        yield


def replace(
    path: Path,
    text: str,
    *,
    unless_changed_from: str | None = None,
    encoding: str | None = None,
    newline: str | None = None,
) -> bool:
    """Write *path* whole, so a reader never sees half of it.

    With *unless_changed_from*, the rename happens only if the file still reads that text
    once the new text is on disk, so only a save in the instant before the rename is lost;
    returns whether it happened. *encoding* and *newline* are `open`'s, for both the write
    and that read: `newline=""` keeps line endings exactly as they are in the text.
    """
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as f:
            f.write(text)
        os.chmod(temp, path.stat().st_mode & 0o7777)
        if unless_changed_from is not None:
            with path.open(encoding=encoding, newline=newline) as f:
                if f.read() != unless_changed_from:
                    Path(temp).unlink(missing_ok=True)
                    return False

        os.replace(temp, path)
        return True
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
