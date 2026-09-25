"""One Markdown inbox per stable lemon ID, with messages claimed by moving to done/."""

import contextlib
import datetime
import fcntl
import os
import tempfile
import time
import uuid
from collections import abc
from pathlib import Path

from .. import brief


def inbox_root() -> Path:
    override = os.environ.get("LEMONAID_MESSAGES_DIR")
    return Path(override) if override else brief.store.briefs_dir() / "inbox"


def inbox_for_id(lemon_id: str) -> Path:
    if not brief.identity.valid(lemon_id):
        raise ValueError(f"Invalid lemon ID: {lemon_id!r}")

    inbox = inbox_root() / lemon_id
    if inbox.is_symlink():
        raise ValueError(f"Inbox is a symlink: {inbox}")

    return inbox


def send(inbox: Path, body: str, sender: str) -> Path:
    if not body.strip():
        raise ValueError("Message cannot be empty")

    if inbox.is_symlink():
        raise ValueError(f"Inbox is a symlink: {inbox}")

    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = inbox / f"{stamp}-{uuid.uuid4().hex}.md"
    sent = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    text = f"From: {sender}\nSent: {sent}\n\n{body.rstrip()}\n"
    fd, temporary = tempfile.mkstemp(dir=inbox, prefix=".message-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

    return path


def _pending(inbox: Path) -> abc.Iterator[Path]:
    if inbox.is_symlink():
        raise ValueError(f"Inbox is a symlink: {inbox}")

    if not inbox.is_dir():
        return

    for path in sorted(inbox.glob("*.md")):
        if path.is_file() and not path.is_symlink():
            yield path


def mark_done(path: Path) -> Path:
    done = path.parent / "done"
    done.mkdir(exist_ok=True)
    claimed = done / path.name
    path.rename(claimed)
    return claimed


@contextlib.contextmanager
def receive_lock(inbox: Path, wait: bool = True) -> abc.Iterator[bool]:
    """Serializes receivers of one inbox.

    Yields False, with nothing to receive, when the inbox does not exist or when
    `wait` is off and another receiver holds it.
    """
    if inbox.is_symlink():
        raise ValueError(f"Inbox is a symlink: {inbox}")

    if not inbox.is_dir():
        yield False
        return

    with open(inbox / ".receive.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return

        yield True


def take_next(inbox: Path) -> tuple[Path, str] | None:
    with receive_lock(inbox) as held:
        return _take_next_locked(inbox) if held else None


def _take_next_locked(inbox: Path) -> tuple[Path, str] | None:
    for path in _pending(inbox):
        try:
            claimed = mark_done(path)
        except FileNotFoundError:
            continue

        try:
            return claimed, claimed.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            restore(claimed)
            raise

    return None


def peek_next(inbox: Path) -> tuple[Path, str] | None:
    """The oldest pending message, left in place for the caller to `mark_done`."""
    for path in _pending(inbox):
        try:
            return path, path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue

    return None


def restore(claimed: Path) -> None:
    claimed.rename(claimed.parent.parent / claimed.name)


def watch_next(
    inbox: Path,
    still_attached: abc.Callable[[], bool],
    timeout: float | None = None,
    interval: float = 0.5,
    find: abc.Callable[[Path], tuple[Path, str] | None] = take_next,
) -> tuple[Path, str]:
    deadline = time.monotonic() + timeout if timeout is not None else None
    while True:
        if not still_attached():
            raise ValueError("Brief is no longer attached to this lemon")

        found = find(inbox)
        if found is not None:
            return found

        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("No message before the watch timeout")

        time.sleep(interval)
