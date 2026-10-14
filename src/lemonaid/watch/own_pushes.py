"""Heads a lemon pushed, so its own `watch pr` waiter does not wake it for them.

GitHub can't say who pushed, since every lemon pushes under its human's account. The
after-tool hook reads a shell call's output instead: `git push` prints one
`<old>..<new>  <src> -> <dst>` line per updated ref (`...` and a leading `+` when
forced). Each `<new>` it finds is kept, newest last, in `<writer dir>/pushes`.
"""

import pathlib
import re
from collections import abc

from . import own_edits

_KEEP = 50
_UPDATED_REF = re.compile(
    r"^\s*\+?\s*[0-9a-f]{7,40}\.\.\.?([0-9a-f]{7,40})\s+\S+\s+->\s+\S+", re.MULTILINE
)
_PUSH_COMMAND = re.compile(r"\bgit(?:\s+-[Cc]\s+\S+|\s+-{1,2}[\w-]+(?:=\S+)?)*\s+push\b")


def is_push(command: str) -> bool:
    return bool(_PUSH_COMMAND.search(command))


def heads_in(output: str) -> list[str]:
    return [m.group(1).lower() for m in _UPDATED_REF.finditer(output)]


def _path(own_root: pathlib.Path, writer: str) -> pathlib.Path:
    return own_edits.writer_dir(own_root, writer) / "pushes"


def _recorded(own_root: pathlib.Path, writer: str) -> list[str]:
    try:
        return _path(own_root, writer).read_text().split()
    except FileNotFoundError:
        return []


def register(own_root: pathlib.Path, writer: str) -> None:
    """Make the writer's directory, which is what lets the installed hook start Python."""
    own_edits.writer_dir(own_root, writer).mkdir(parents=True, exist_ok=True)


def record(own_root: pathlib.Path, writer: str, heads: abc.Iterable[str]) -> None:
    heads = list(heads)
    if not heads:
        return

    path = _path(own_root, writer)
    with own_edits.locked(path):
        path.write_text("".join(f"{h}\n" for h in [*_recorded(own_root, writer), *heads][-_KEEP:]))


def is_own(own_root: pathlib.Path, writer: str, head: str) -> bool:
    """Whether `head` (a full SHA) is one the writer's recorded pushes abbreviate."""
    return bool(writer) and any(head.startswith(h) for h in _recorded(own_root, writer))
