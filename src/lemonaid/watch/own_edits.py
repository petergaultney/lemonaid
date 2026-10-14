"""Edits a lemon made to a doc it watches, so its own waiter does not wake it for them.

An edit is recorded as a numbered transition between two body digests (the body outside
comment threads, see relay_comments.body_without_threads) under the writer's key, per doc.
The waiter replays, in order, the transitions it has not yet consumed, starting from the
body it last reported, and adopts a changed body silently only when that chain reaches it.
Anyone else's change on the way, a human's edit made earlier in the same turn included,
breaks the chain and wakes it as before.

Claude Code's and Codex's PreToolUse and PostToolUse hooks record a transition for each
watched doc that a tool call changed, whatever the tool. `watch doc --editing` before an
edit and `--mine` after it do the same where no hook is installed.

Layout, under `<lemonaid state dir>/own-edits/<writer>/` (see `root`):
- `<doc key>.doc`: the doc's resolved path; a waiter writes it, and the hook records
  edits only to docs that have one
- `<doc key>.edits`: one `<seq> <before> <after>` transition per line, oldest first
- `pending/<key>`: the before digest, until the edit's after side is recorded (at most 10 minutes)
"""

import contextlib
import fcntl
import hashlib
import os
import pathlib
import time
from collections import abc

from . import body_norm, relay_comments

_KEEP = 50
_PENDING_MAX_AGE = 600.0  # seconds; an --editing whose edit failed must not pair with a later one


def claude_writer(session_id: str) -> str:
    return f"claude-{session_id}"


def writer_from_env(env: abc.Mapping[str, str], codex_thread: str = "") -> str:
    """The calling lemon's key, or "" when the environment names no harness session.

    A waiter delivering to `codex_thread` serves that thread's lemon.
    """
    if codex_thread:
        return f"codex-{codex_thread}"

    if session_id := env.get("CLAUDE_CODE_SESSION_ID"):
        return claude_writer(session_id)

    if thread_id := env.get("CODEX_THREAD_ID"):
        return f"codex-{thread_id}"

    return ""


def root() -> pathlib.Path:
    """Where every writer's records live; the installed hook command checks the same path."""
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return pathlib.Path(state).expanduser() / "own-edits"


def writer_dir(own_root: pathlib.Path, writer: str) -> pathlib.Path:
    return own_root / writer


def _doc_key(doc: pathlib.Path) -> str:
    return hashlib.sha1(str(doc.resolve()).encode()).hexdigest()[:16]


def _edits_path(own_root: pathlib.Path, writer: str, doc: pathlib.Path) -> pathlib.Path:
    return writer_dir(own_root, writer) / f"{_doc_key(doc)}.edits"


def body_digest(body: str) -> str:
    return hashlib.sha256(body_norm.normalized(body).encode()).hexdigest()[:16]


def _file_digest(doc: pathlib.Path) -> str:
    try:
        text = doc.read_text()
    except FileNotFoundError:
        text = ""
    return body_digest(relay_comments.body_without_threads(text))


@contextlib.contextmanager
def locked(path: pathlib.Path) -> abc.Iterator[None]:
    """Serialize read-modify-write of `path` across parallel tool calls' hooks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(f".{path.name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def unregister(own_root: pathlib.Path, writer: str, doc: pathlib.Path) -> None:
    (writer_dir(own_root, writer) / f"{_doc_key(doc)}.doc").unlink(missing_ok=True)


def register(own_root: pathlib.Path, writer: str, doc: pathlib.Path) -> None:
    path = writer_dir(own_root, writer) / f"{_doc_key(doc)}.doc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(doc.resolve()))


def watched(own_root: pathlib.Path, writer: str) -> list[pathlib.Path]:
    """The docs the writer's waiters registered."""
    found = []
    for path in sorted(writer_dir(own_root, writer).glob("*.doc")):
        try:
            found.append(pathlib.Path(path.read_text()))
        except FileNotFoundError:
            continue
    return found


def _transitions(path: pathlib.Path) -> list[tuple[int, str, str]]:
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return []

    return [
        (int(fields[0]), fields[1], fields[2])
        for fields in (line.split() for line in lines)
        if len(fields) == 3 and fields[0].isdigit()
    ]


def _append(path: pathlib.Path, before: str, after: str) -> None:
    seq = max((t[0] for t in _transitions(path)), default=0) + 1
    with path.open("a") as f:
        f.write(f"{seq} {before} {after}\n")
    lines = path.read_text().splitlines()
    if len(lines) > 2 * _KEEP:
        path.write_text("".join(f"{line}\n" for line in lines[-_KEEP:]))


def _pending(own_root: pathlib.Path, writer: str, key: str) -> pathlib.Path:
    return writer_dir(own_root, writer) / "pending" / key


def cli_key(doc: pathlib.Path) -> str:
    """The pending key `--editing` and `--mine` share for one doc."""
    return f"cli-{_doc_key(doc)}"


def tool_key(tool_use_id: str, doc: pathlib.Path) -> str:
    """The pending key a tool call's before and after hooks share for one doc."""
    return f"{tool_use_id}-{_doc_key(doc)}"


def _sweep(pending: pathlib.Path) -> None:
    """Drop before digests whose after side never came (a failed call runs no PostToolUse)."""
    for stale in pending.iterdir():
        try:
            if time.time() - stale.stat().st_mtime > _PENDING_MAX_AGE:
                stale.unlink()
        except FileNotFoundError:
            continue


def before_edit(own_root: pathlib.Path, writer: str, key: str, doc: pathlib.Path) -> None:
    path = _pending(own_root, writer, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    _sweep(path.parent)
    path.write_text(_file_digest(doc))


def after_edit(own_root: pathlib.Path, writer: str, key: str, doc: pathlib.Path) -> bool:
    """Record the edit whose before digest `before_edit` kept; without one, record nothing."""
    path = _pending(own_root, writer, key)
    try:
        before = path.read_text().strip()
        fresh = time.time() - path.stat().st_mtime < _PENDING_MAX_AGE
    except FileNotFoundError:
        return False

    path.unlink()
    if not fresh:
        return False

    after, edits = _file_digest(doc), _edits_path(own_root, writer, doc)
    with locked(edits):
        if before != after and (before, after) != next(
            ((b, a) for _, b, a in sorted(_transitions(edits))[-1:]), None
        ):
            _append(edits, before, after)  # parallel tool calls each see the same change
    # Two parallel calls that both edit the doc record two transitions from the same
    # before digest, which don't chain, so the waiter wakes: a false wake, never a lost one.
    return True


def transitions(
    own_root: pathlib.Path, writer: str, doc: pathlib.Path
) -> list[tuple[int, str, str]]:
    """The writer's recorded `(seq, before, after)` edits to `doc`, oldest first."""
    return _transitions(_edits_path(own_root, writer, doc))
