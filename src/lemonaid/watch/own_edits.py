"""Edits a lemon made to a doc it watches, so its own waiter does not wake it for them.

An edit is recorded as a numbered transition between two body digests (the body outside
comment threads, see relay_comments.body_without_threads) under the writer's key, per doc.
The waiter replays, in order, the transitions it has not yet consumed, starting from the
body it last reported, and adopts a changed body silently only when that chain reaches it.
Anyone else's change on the way, a human's edit made earlier in the same turn included,
breaks the chain and wakes it as before.

Claude Code's PreToolUse and PostToolUse hooks record each transition. For edits made
through a shell or by Codex, `watch doc --editing` before the edit and `--mine` after it
do the same.

Layout, under `<state dir>/own/<writer>/`:
- `<doc key>.doc`: the doc's resolved path; a waiter writes it, and the hook records
  edits only to docs that have one
- `<doc key>.edits`: one `<seq> <before> <after>` transition per line, oldest first
- `pending/<key>`: the before digest, until the edit's after side is recorded
"""

import hashlib
import pathlib
from collections import abc

from . import relay_comments

_KEEP = 50


def claude_writer(session_id: str) -> str:
    return f"claude-{session_id}"


def writer_from_env(env: abc.Mapping[str, str]) -> str:
    """The calling lemon's key, or "" when the environment names no harness session."""
    if session_id := env.get("CLAUDE_CODE_SESSION_ID"):
        return claude_writer(session_id)

    if thread_id := env.get("CODEX_THREAD_ID"):
        return f"codex-{thread_id}"

    return ""


def writer_dir(state_dir: pathlib.Path, writer: str) -> pathlib.Path:
    return state_dir / "own" / writer


def _doc_key(doc: pathlib.Path) -> str:
    return hashlib.sha1(str(doc.resolve()).encode()).hexdigest()[:16]


def _edits_path(state_dir: pathlib.Path, writer: str, doc: pathlib.Path) -> pathlib.Path:
    return writer_dir(state_dir, writer) / f"{_doc_key(doc)}.edits"


def body_digest(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def _file_digest(doc: pathlib.Path) -> str:
    try:
        text = doc.read_text()
    except FileNotFoundError:
        text = ""
    return body_digest(relay_comments.body_without_threads(text))


def register(state_dir: pathlib.Path, writer: str, doc: pathlib.Path) -> None:
    path = writer_dir(state_dir, writer) / f"{_doc_key(doc)}.doc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(doc.resolve()))


def watched(state_dir: pathlib.Path, writer: str, doc: pathlib.Path) -> bool:
    return (writer_dir(state_dir, writer) / f"{_doc_key(doc)}.doc").exists()


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
    path.parent.mkdir(parents=True, exist_ok=True)
    seq = max((t[0] for t in _transitions(path)), default=0) + 1
    with path.open("a") as f:
        f.write(f"{seq} {before} {after}\n")
    lines = path.read_text().splitlines()
    if len(lines) > 2 * _KEEP:
        path.write_text("".join(f"{line}\n" for line in lines[-_KEEP:]))


def _pending(state_dir: pathlib.Path, writer: str, key: str) -> pathlib.Path:
    return writer_dir(state_dir, writer) / "pending" / key


def cli_key(doc: pathlib.Path) -> str:
    """The pending key `--editing` and `--mine` share for one doc."""
    return f"cli-{_doc_key(doc)}"


def before_edit(state_dir: pathlib.Path, writer: str, key: str, doc: pathlib.Path) -> None:
    path = _pending(state_dir, writer, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_file_digest(doc))


def after_edit(state_dir: pathlib.Path, writer: str, key: str, doc: pathlib.Path) -> bool:
    """Record the edit whose before digest `before_edit` kept; without one, record nothing."""
    path = _pending(state_dir, writer, key)
    try:
        before = path.read_text().strip()
    except FileNotFoundError:
        return False

    path.unlink()
    _append(_edits_path(state_dir, writer, doc), before, _file_digest(doc))
    return True


def last_seq(state_dir: pathlib.Path, writer: str, doc: pathlib.Path) -> int:
    return max((t[0] for t in _transitions(_edits_path(state_dir, writer, doc))), default=0)


def chain_to(
    transitions: abc.Iterable[tuple[int, str, str]], consumed: int, start: str, goal: str
) -> int | None:
    """The last seq, if every transition after `consumed`, in order, chains from `start` and ends at `goal`.

    A transition that doesn't start where the previous one ended means someone else changed
    the doc in between, so nothing is accounted for.
    """
    current, last = start, consumed
    for seq, before, after in sorted(t for t in transitions if t[0] > consumed):
        if before != current:
            return None

        current, last = after, seq
    return last if current == goal and last > consumed else None


def settles(
    state_dir: pathlib.Path,
    writer: str,
    doc: pathlib.Path,
    consumed: int,
    settled_body: str,
    body: str,
) -> int | None:
    """The seq through which the writer's own edits account for every change from `settled_body` to `body`."""
    return chain_to(
        _transitions(_edits_path(state_dir, writer, doc)),
        consumed,
        body_digest(settled_body),
        body_digest(body),
    )
