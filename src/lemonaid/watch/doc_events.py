"""Cursor-aware document events, including advisory notices when a document disappears."""

import dataclasses
import enum
import hashlib
import json
import pathlib
import typing as ty
from collections import abc

from . import (
    body_norm,
    cursors,
    doc_body,
    own_edits,
    own_edits_replay,
    path_presence,
    relay_comments,
    signature,
)


class Outcome(enum.Enum):
    NOTHING = "nothing"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclasses.dataclass
class DocWatch:
    doc: pathlib.Path
    own_root: pathlib.Path
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
    presence: path_presence.Presence
    all_threads: bool = False
    settled_quiet: float = 0  # quiet period enforced outside this detector


def state_stem(state_dir: pathlib.Path, doc: pathlib.Path, me: str) -> pathlib.Path:
    return state_dir / hashlib.sha1(f"{doc.resolve()}\0{me}".encode()).hexdigest()[:16]


def _thread_key(thread: str) -> str:
    return hashlib.sha1(body_norm.normalized(thread).encode()).hexdigest()[:16]


def _load_reported(path: pathlib.Path) -> set[str]:
    try:
        return set(json.loads(path.read_text()))
    except (OSError, ValueError):
        return set()


def _load_settled(path: pathlib.Path, doc: pathlib.Path) -> str:
    """The body as of the last reported edit; the first waiter for a doc takes its current body.

    A doc that doesn't exist yet has an empty body, so writing it is reported as its creation.
    """
    try:
        return path.read_text()
    except OSError:
        pass
    try:
        text = doc.read_text()
    except FileNotFoundError:
        text = ""
    body = relay_comments.body_without_threads(text)
    cursors.write_text(path, body)
    return body


def _load_consumed(
    path: pathlib.Path, own_root: pathlib.Path, writer: str, doc: pathlib.Path
) -> int:
    """The consumed seq saved for this writer; a new writer starts after its existing edits."""
    try:
        saved_writer, seq = path.read_text().split()
        if saved_writer == writer:
            return int(seq)

    except (OSError, ValueError):
        pass
    seq = own_edits_replay.last_seq(own_root, writer, doc)
    cursors.write_text(path, f"{writer} {seq}")
    return int(seq)


def open_watch(
    state_dir: pathlib.Path,
    doc: pathlib.Path,
    me: str,
    legacy: abc.Iterable[str],
    edits: bool,
    quiet: float,
    writer: str = "",
    own_root: pathlib.Path | None = None,
    cursor_key: str | None = None,
) -> DocWatch:
    """`writer`, when set, is the watching lemon's own_edits key: body edits it made don't wake it.

    The cursors are keyed by doc and `cursor_key`, by default `me`; a waiter using its
    lemon's own cursor directory passes "". `own_root` is where own_edits keeps the
    writer's records (default: own_edits.root()).
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    own_root = own_root or own_edits.root()
    if writer and edits:
        own_edits.register(own_root, writer, doc)
    stem = state_stem(state_dir, doc, me if cursor_key is None else cursor_key)
    settled_path = stem.with_suffix(".settled.md")
    settled_body = _load_settled(settled_path, doc) if edits else ""
    consumed_path = stem.with_suffix(".consumed")
    consumed = _load_consumed(consumed_path, own_root, writer, doc) if writer and edits else 0
    return DocWatch(
        doc=doc,
        own_root=own_root,
        writer=writer,
        mine=signature.forms([me, *legacy]),
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
        presence=path_presence.open_watch(stem, doc, seen=bool(settled_body)),
    )


def _settle(w: DocWatch, body: str, consumed: int) -> None:
    w.settled_body = w.pending_body = body
    cursors.write_text(w.settled_path, body)
    if w.writer and consumed != w.consumed:
        w.consumed = consumed
        cursors.write_text(w.consumed_path, f"{w.writer} {consumed}")


def poll(w: DocWatch, deliver: ty.Callable[[str], bool]) -> Outcome:
    """Read the doc once and deliver at most one event; state advances only when `deliver` returns True."""
    try:
        text = w.doc.read_text()
        path_presence.observe(w.presence)
    except FileNotFoundError:
        result = path_presence.report_missing(w.presence, max(w.quiet, w.settled_quiet), deliver)
        return {None: Outcome.NOTHING, False: Outcome.FAILED, True: Outcome.DELIVERED}[result]

    except OSError as e:
        print(f"cannot read {w.doc}: {e}", flush=True)
        return Outcome.NOTHING

    threads = {_thread_key(t): t for t in relay_comments.unanswered_threads(text, w.mine)}
    new = [t for k, t in threads.items() if k not in w.reported]
    messages = (
        [
            f"{len(new)} new or changed unanswered thread(s) in {w.doc} ({len(threads)} unanswered in all); "
            + "; ".join(
                relay_comments.thread_gist(t)
                for t in (threads.values() if w.all_threads else new[:3])
            )
        ]
        if new
        else []
    )
    body = relay_comments.body_without_threads(text)
    edit, consumed = (
        doc_body.changed(w, body, lambda consumed: _settle(w, body, consumed))
        if w.edits
        else ("", w.consumed)
    )
    if edit:
        messages.append(edit)
    if messages and not deliver("; ".join(messages)):
        return Outcome.FAILED

    if set(threads) != w.reported:
        w.reported = set(threads)
        cursors.write_json(w.reported_path, sorted(w.reported))
    if edit:
        _settle(w, body, consumed)
    return Outcome.DELIVERED if messages else Outcome.NOTHING
