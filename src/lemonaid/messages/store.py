"""One Markdown inbox per stable lemon ID, with messages claimed by moving to done/."""

import datetime
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


def take_next(inbox: Path) -> tuple[Path, str] | None:
    if inbox.is_symlink():
        raise ValueError(f"Inbox is a symlink: {inbox}")

    if not inbox.is_dir():
        return None

    for path in sorted(inbox.glob("*.md")):
        if not path.is_file() or path.is_symlink():
            continue

        done = inbox / "done"
        done.mkdir(exist_ok=True)
        claimed = done / path.name
        try:
            path.rename(claimed)
        except FileNotFoundError:
            continue

        try:
            return claimed, claimed.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            restore(claimed)
            raise

    return None


def restore(claimed: Path) -> None:
    claimed.rename(claimed.parent.parent / claimed.name)


def watch_next(
    inbox: Path,
    still_attached: abc.Callable[[], bool],
    timeout: float | None = None,
    interval: float = 0.5,
) -> tuple[Path, str]:
    deadline = time.monotonic() + timeout if timeout is not None else None
    while True:
        if not still_attached():
            raise ValueError("Brief is no longer attached to this lemon")

        found = take_next(inbox)
        if found is not None:
            return found

        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("No message before the watch timeout")

        time.sleep(interval)
