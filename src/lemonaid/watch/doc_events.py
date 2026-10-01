"""Event detection for one watched document, independent of how events are delivered.

A `DocWatch` holds what has already been reported for (doc, signer). Its state lives in
a state directory, by default $TMPDIR/watch-doc, so a restarted waiter, or a different
waiter under the same signer, does not re-report a thread nobody has touched since. The
file names match the standalone watch-doc.py, so the two share state and locks.
"""

import dataclasses
import difflib
import enum
import hashlib
import json
import pathlib
import tempfile
import time
import typing as ty
from collections import abc

from . import own_edits, relay_comments


def default_state_dir() -> pathlib.Path:
    return (
        pathlib.Path(tempfile.gettempdir()) / "watch-doc"
    )  # writable in Codex's sandbox; ~/.cache is not


class Outcome(enum.Enum):
    NOTHING = "nothing"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclasses.dataclass
class DocWatch:
    doc: pathlib.Path
    state_dir: pathlib.Path
    writer: str
    mine: frozenset[str]
    edits: bool
    quiet: float
    reported_path: pathlib.Path
    settled_path: pathlib.Path
    consumed_path: pathlib.Path
    consumed: int  # the last of the writer's own_edits transitions the settled body accounts for
    reported: set[str]
    settled_body: str
    pending_body: str
    pending_since: float


def state_stem(state_dir: pathlib.Path, doc: pathlib.Path, me: str) -> pathlib.Path:
    return state_dir / hashlib.sha1(f"{doc.resolve()}\0{me}".encode()).hexdigest()[:16]


def _thread_key(thread: str) -> str:
    return hashlib.sha1(thread.encode()).hexdigest()[:16]


def _load_reported(path: pathlib.Path) -> set[str]:
    try:
        return set(json.loads(path.read_text()))
    except (OSError, ValueError):
        return set()


def _load_settled(path: pathlib.Path, doc: pathlib.Path) -> str:
    """The body as of the last reported edit; the first waiter for a doc takes its current body."""
    try:
        return path.read_text()
    except OSError:
        body = relay_comments.body_without_threads(doc.read_text())
        path.write_text(body)
        return body


def _load_consumed(
    path: pathlib.Path, state_dir: pathlib.Path, writer: str, doc: pathlib.Path
) -> int:
    """The consumed seq saved for this writer; a new writer starts after its existing edits."""
    try:
        saved_writer, seq = path.read_text().split()
        if saved_writer == writer:
            return int(seq)

    except (OSError, ValueError):
        pass
    seq = own_edits.last_seq(state_dir, writer, doc)
    path.write_text(f"{writer} {seq}")
    return int(seq)


def _line_delta(old: str, new: str) -> str:
    added = removed = 0
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return f"+{added}/-{removed} lines"


def open_watch(
    state_dir: pathlib.Path,
    doc: pathlib.Path,
    me: str,
    legacy: abc.Iterable[str],
    edits: bool,
    quiet: float,
    writer: str = "",
) -> DocWatch:
    """`writer`, when set, is the watching lemon's own_edits key: body edits it made don't wake it."""
    state_dir.mkdir(parents=True, exist_ok=True)
    if writer and edits:
        own_edits.register(state_dir, writer, doc)
    stem = state_stem(state_dir, doc, me)
    settled_path = stem.with_suffix(".settled.md")
    settled_body = _load_settled(settled_path, doc) if edits else ""
    consumed_path = stem.with_suffix(".consumed")
    consumed = _load_consumed(consumed_path, state_dir, writer, doc) if writer and edits else 0
    return DocWatch(
        doc=doc,
        state_dir=state_dir,
        writer=writer,
        mine=frozenset({me, *legacy}),
        edits=edits,
        quiet=quiet,
        reported_path=stem.with_suffix(".reported.json"),
        settled_path=settled_path,
        consumed_path=consumed_path,
        consumed=consumed,
        reported=_load_reported(stem.with_suffix(".reported.json")),
        settled_body=settled_body,
        pending_body=settled_body,
        pending_since=0.0,
    )


def _settle(w: DocWatch, body: str, consumed: int) -> None:
    w.settled_body = w.pending_body = body
    w.settled_path.write_text(body)
    if w.writer and consumed != w.consumed:
        w.consumed = consumed
        w.consumed_path.write_text(f"{w.writer} {consumed}")


def poll(w: DocWatch, deliver: ty.Callable[[str], bool]) -> Outcome:
    """Read the doc once and deliver at most one event; state advances only when `deliver` returns True."""
    try:
        text = w.doc.read_text()
    except OSError as e:
        print(f"cannot read {w.doc}: {e}", flush=True)
        return Outcome.NOTHING

    threads = {_thread_key(t): t for t in relay_comments.unanswered_threads(text, w.mine)}
    new = [t for k, t in threads.items() if k not in w.reported]
    if new and not deliver(
        f"{len(new)} new or changed unanswered thread(s) in {w.doc} ({len(threads)} unanswered in all); "
        + "; ".join(relay_comments.thread_gist(t) for t in new[:3])
    ):
        return Outcome.FAILED

    if set(threads) != w.reported:
        w.reported = set(threads)
        w.reported_path.write_text(json.dumps(sorted(w.reported)))
    if new:
        return Outcome.DELIVERED

    if not w.edits:
        return Outcome.NOTHING

    body = relay_comments.body_without_threads(text)
    own = (
        own_edits.settles(w.state_dir, w.writer, w.doc, w.consumed, w.settled_body, body)
        if w.writer
        else None
    )
    if own is not None:
        _settle(w, body, own)
        return Outcome.NOTHING

    if body == w.settled_body:
        w.pending_body = body
        return Outcome.NOTHING

    if body != w.pending_body:
        w.pending_body, w.pending_since = body, time.time()
        return Outcome.NOTHING

    if time.time() - w.pending_since < w.quiet:
        return Outcome.NOTHING

    if not deliver(
        f"body of {w.doc} changed ({_line_delta(w.settled_body, body)}), quiet for {int(w.quiet)}s"
    ):
        return Outcome.FAILED

    _settle(w, body, own_edits.last_seq(w.state_dir, w.writer, w.doc) if w.writer else 0)
    return Outcome.DELIVERED
