"""Whether an open buffer and its file still hold the text they last shared, which decides
where a lemon's write goes and when an edit to the buffer is refused."""

import typing as ty
from pathlib import Path

from pygls.workspace import TextDocument

from .documents import CommentsServer, key

BufferState = ty.Literal["clean", "unsaved", "diverged"]

DIVERGED: ty.Final = (
    "the file changed on disk since your buffer last matched it; save or reload the file,"
    " then try again"
)


def note(ls: CommentsServer, document: TextDocument) -> None:
    """Remember the buffer's text and the file's whenever they match: on open, on save, and
    when the editor reloads the file after a lemon wrote it. A buffer that doesn't match
    its file when it opens takes the file's text at that moment as its baseline."""
    on_disk = _disk_text(document.path)
    if on_disk is not None and _same_text(document.source, on_disk):
        ls.in_sync[key(document.uri)] = document.source
        ls.disk_baseline[key(document.uri)] = on_disk
    else:
        ls.disk_baseline.setdefault(key(document.uri), on_disk)


def state(ls: CommentsServer, document: TextDocument) -> BufferState:
    """`clean`: the buffer holds the text it last shared with the file, so a write goes to
    the file and the editor reloads. The file may have moved on already: after a lemon
    writes it, the buffer differs from it until the editor reloads, and a second write in
    that moment must go to the file too, or the comments end up split between the two.
    `unsaved`: only the buffer has changed, so a write goes to the buffer. `diverged`:
    both have, so either write would leave the two copies with different comments, and
    we refuse until you save or reload.
    """
    in_sync = ls.in_sync.get(key(document.uri))
    if in_sync is not None and _same_text(document.source, in_sync):
        return "clean"
    return "diverged" if disk_moved(ls, document) else "unsaved"


def disk_moved(ls: CommentsServer, document: TextDocument) -> bool:
    """Whether the file has changed since its baseline. An edit to the buffer is then
    refused, clean buffer or not: the editor hasn't reloaded yet, and the edit would leave
    the file and the buffer with different comments."""
    baseline = ls.disk_baseline.get(key(document.uri))
    on_disk = _disk_text(document.path)
    if baseline is None or on_disk is None:
        return baseline != on_disk
    return not _same_text(on_disk, baseline)


def _same_text(buffer: str, on_disk: str) -> bool:
    """Editors report a buffer with the line endings and final newline they will write,
    which may differ from the file's."""

    def normalized(text: str) -> str:
        return text.replace("\r\n", "\n").removesuffix("\n")

    return normalized(buffer) == normalized(on_disk)


def _disk_text(path: str) -> str | None:
    try:
        return Path(path).read_bytes().decode()
    except (OSError, UnicodeDecodeError):
        return None
