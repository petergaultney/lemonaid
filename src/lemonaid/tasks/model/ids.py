"""Parsing a task's identifying values: task IDs, tagged holders and subject URLs."""

import urllib.parse
import uuid
from pathlib import Path


def holder(text: str) -> str:
    """*text* as a tagged holder, which is always a brief: a task names the lemon whose
    move it is, and a person's turn is a brief's Status. Raises ValueError for anything else."""
    kind, _, name = text.partition(":")
    if kind != "brief" or not name:
        raise ValueError(f"holder {text!r} must be brief:ID; a task is held by a lemon")

    return f"{kind}:{name}"


def subject_url(text: str) -> str:
    """Empty, or one absolute URL or URI; stored as data, never opened. An absolute file
    path is stored as its `file://` URL."""
    if text.startswith(("/", "~/")):
        return Path(text).expanduser().as_uri()

    if text and not urllib.parse.urlparse(text).scheme:
        raise ValueError(f"{text!r} is not an absolute URL, URI or file path")

    return text


def task_id(text: str) -> str:
    """The UUID in `task:<uuid>` or a bare UUID; raises ValueError for anything else."""
    return str(uuid.UUID(text.removeprefix("task:")))
