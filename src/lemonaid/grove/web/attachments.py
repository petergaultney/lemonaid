"""Files a browser attaches to a message for a lemon, kept on the server's disk.

A page uploads each file as soon as it is picked, and sends only its id with the message, so a
draft's attachments survive the page being drawn again. Each file is kept as
`attachments/<id>/<name>` under lemonaid's state directory, where a terminal lemon reads it by
the path its message gives. Files older than *KEEP_DAYS* go at the next upload.
"""

import base64
import binascii
import os
import re
import secrets
import shutil
import time
import typing as ty
from collections import abc
from pathlib import Path

from ...log import get_logger

_log = get_logger("grove.web.attachments")

MAX_BYTES = 20 * 1024 * 1024  # OpenClaw's own default ceiling for a chat attachment
MAX_PER_MESSAGE = 10
KEEP_DAYS = 30
_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")
_NAME_CHARS = 100


class Attached(ty.NamedTuple):
    id: str
    name: str
    mime: str
    path: Path


def _root() -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
    return state / "attachments"


def safe_name(name: str) -> str:
    """*name*'s last part, with only letters, digits, `.`, `_`, `-` and spaces, never hidden."""
    base = re.split(r"[\\/]", name)[-1]
    cleaned = _UNSAFE.sub("_", base).strip(" .")
    if len(cleaned) > _NAME_CHARS:
        _, dot, suffix = cleaned.rpartition(".")
        keep = f"{dot}{suffix}" if dot and len(suffix) <= 10 else ""
        cleaned = cleaned[: _NAME_CHARS - len(keep)] + keep
    return cleaned or "file"


def _prune(root: Path, now: float) -> None:
    for each in root.iterdir() if root.is_dir() else ():
        try:
            old = now - each.stat().st_mtime > KEEP_DAYS * 86400
        except OSError:
            continue
        if old and _ID.match(each.name):
            shutil.rmtree(each, ignore_errors=True)
            _log.info("removed an attachment kept past %d days: %s", KEEP_DAYS, each.name)


def save(name: str, mime: str, content: str) -> dict | str:
    """Keep the file *content* (base64) names, returning what the page shows of it, or why not."""
    try:
        raw = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError):
        return "the file didn't arrive whole"

    if not raw:
        return f"{name} is empty"

    if len(raw) > MAX_BYTES:
        return f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB"

    root, now = _root(), time.time()
    _prune(root, now)
    found_id = f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}-{secrets.token_hex(4)}"
    path = root / found_id / safe_name(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    (path.parent / ".mime").write_text(mime or "application/octet-stream")
    return {"id": found_id, "name": path.name, "size": len(raw), "mime": mime}


def _found(found_id: str) -> Attached | None:
    if not _ID.match(found_id):
        return None

    folder = _root() / found_id
    files = (
        [each for each in folder.iterdir() if not each.name.startswith(".")]
        if folder.is_dir()
        else []
    )
    if len(files) != 1:
        return None

    try:
        mime = (folder / ".mime").read_text().strip()
    except OSError:
        mime = ""
    return Attached(found_id, files[0].name, mime or "application/octet-stream", files[0])


def found(ids: abc.Iterable[str]) -> list[Attached] | str:
    """The kept files *ids* name, in order, or why one can't be sent."""
    wanted = list(ids)
    if len(wanted) > MAX_PER_MESSAGE:
        return f"a message takes at most {MAX_PER_MESSAGE} files"

    out = []
    for each in wanted:
        attached = _found(str(each))
        if attached is None:
            return "an attachment is gone from the server; remove it and attach it again"
        out.append(attached)
    return out


def drop(found_id: str) -> str:
    """Forget a file the page removed from its draft. Returns "" either way."""
    attached = _found(found_id)
    if attached is not None:
        shutil.rmtree(attached.path.parent, ignore_errors=True)
    return ""


def as_text(text: str, files: abc.Sequence[Attached]) -> str:
    """*text* with each file's path after it, for a lemon that reads files from disk."""
    if not files:
        return text

    listed = "\n".join(f"- {each.path}" for each in files)
    head = "Attached file:" if len(files) == 1 else "Attached files:"
    return f"{text.rstrip()}\n\n{head}\n{listed}" if text.strip() else f"{head}\n{listed}"


def for_chat(files: abc.Sequence[Attached]) -> list[dict]:
    """*files* as OpenClaw's `chat.send` takes them."""
    return [
        {
            "type": "image" if each.mime.startswith("image/") else "file",
            "mimeType": each.mime,
            "fileName": each.name,
            "content": base64.b64encode(each.path.read_bytes()).decode(),
        }
        for each in files
    ]
