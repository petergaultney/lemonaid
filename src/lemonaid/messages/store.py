"""One Markdown mailbox per stable lemon ID, with messages claimed by moving to done/."""

import contextlib
import datetime
import fcntl
import os
import tempfile
import time
import uuid
from collections import abc
from pathlib import Path

from .. import brief, home

FORWARD = ".forward"  # in a mailbox left behind by a reroll: the Lemon-ID it moved to
_MAX_HOPS = 16


def _mailbox_parent() -> Path | None:
    """The folder holding `mailbox/`, when it may still hold a pre-0.142 `inbox/`."""
    if os.environ.get("LEMONAID_MESSAGES_DIR"):
        return None

    if os.environ.get("LEMONAID_BRIEFS_DIR"):
        return brief.store.briefs_dir()

    return home.layout.lemons_dir() if home.layout.cut_over() else None


def mailbox_root() -> Path:
    if override := os.environ.get("LEMONAID_MESSAGES_DIR"):
        return Path(override)

    if parent := _mailbox_parent():
        home.mailbox_move.move(parent)
        return parent / home.layout.MAILBOX

    return home.layout.mailbox_root()


def _refusal() -> str:
    parent = _mailbox_parent()
    return home.layout.paused() or (home.mailbox_move.split(parent) if parent else "")


def mailbox_for_id(lemon_id: str) -> Path:
    if paused := home.layout.paused():
        raise ValueError(paused)

    if not brief.identity.valid(lemon_id):
        raise ValueError(f"Invalid lemon ID: {lemon_id!r}")

    mailbox = mailbox_root() / lemon_id
    if refused := _refusal():
        raise ValueError(refused)

    if mailbox.is_symlink():
        raise ValueError(f"Mailbox is a symlink: {mailbox}")

    return mailbox


def forwarded(mailbox: Path) -> Path:
    """Where *mailbox*'s messages go now, following rerolls."""
    for _ in range(_MAX_HOPS):
        try:
            lemon_id = (mailbox / FORWARD).read_text().strip()
        except FileNotFoundError:
            return mailbox

        mailbox = mailbox_for_id(lemon_id)

    raise ValueError(f"Mailbox forwards more than {_MAX_HOPS} times: {mailbox}")


def _write(mailbox: Path, body: str, sender: str, key: str = "") -> Path:
    mailbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = mailbox / f"{stamp}-{key or uuid.uuid4().hex}.md"
    sent = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    text = f"From: {sender}\nSent: {sent}\n\n{body.rstrip()}\n"
    fd, temporary = tempfile.mkstemp(dir=mailbox, prefix=".message-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

    return path


def send(mailbox: Path, body: str, sender: str, key: str = "") -> Path:
    """*key*, a hex string, names the message in place of a random one, so a sender can find
    its receipt again without keeping the ID."""
    if not body.strip():
        raise ValueError("Message cannot be empty")

    if key and not all(c in "0123456789abcdef" for c in key):
        raise ValueError(f"Message key must be lowercase hex: {key!r}")

    with home.guard.operation():
        mailbox = forwarded(mailbox)
        if refused := _refusal():
            raise ValueError(refused)

        if mailbox.is_symlink():
            raise ValueError(f"Mailbox is a symlink: {mailbox}")

        return _write(mailbox, body, sender, key)


def _pending(mailbox: Path) -> abc.Iterator[Path]:
    if mailbox.is_symlink():
        raise ValueError(f"Mailbox is a symlink: {mailbox}")

    if not mailbox.is_dir():
        return

    for path in sorted(mailbox.glob("*.md")):
        if path.is_file() and not path.is_symlink():
            yield path


def pending_count(mailbox: Path) -> int:
    return sum(1 for _ in _pending(mailbox))


def mark_done(path: Path) -> Path:
    """Move a received message to done/, its modified time becoming when it was received."""
    done = path.parent / "done"
    done.mkdir(exist_ok=True)
    claimed = done / path.name
    path.rename(claimed)
    os.utime(claimed)
    return claimed


@contextlib.contextmanager
def receive_lock(mailbox: Path, wait: bool = True) -> abc.Iterator[bool]:
    """Serializes receivers of one mailbox.

    Yields False, with nothing to receive, when the mailbox does not exist or when
    `wait` is off and another receiver holds it.
    """
    if mailbox.is_symlink():
        raise ValueError(f"Mailbox is a symlink: {mailbox}")

    if not mailbox.is_dir():
        yield False
        return

    with open(mailbox / ".receive.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return

        yield True


def take_next(mailbox: Path) -> tuple[Path, str] | None:
    with home.guard.operation(), receive_lock(mailbox) as held:
        return _take_next_locked(mailbox) if held else None


def _take_next_locked(mailbox: Path) -> tuple[Path, str] | None:
    for path in _pending(mailbox):
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


def peek_next(mailbox: Path) -> tuple[Path, str] | None:
    """The oldest pending message, left in place for the caller to `mark_done`."""
    for path in _pending(mailbox):
        try:
            return path, path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue

    return None


def restore(claimed: Path) -> None:
    claimed.rename(claimed.parent.parent / claimed.name)


def watch_next(
    mailbox: Path,
    still_attached: abc.Callable[[], bool],
    timeout: float | None = None,
    interval: float = 0.5,
    find: abc.Callable[[Path], tuple[Path, str] | None] = take_next,
) -> tuple[Path, str]:
    deadline = time.monotonic() + timeout if timeout is not None else None
    while True:
        if not still_attached():
            raise ValueError("Brief is no longer attached to this lemon")

        found = find(mailbox)
        if found is not None:
            return found

        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("No message before the watch timeout")

        time.sleep(interval)
