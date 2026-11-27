"""Cursor-aware document events, including advisory notices when a document disappears."""

import dataclasses
import enum
import hashlib
import pathlib
import typing as ty
from collections import abc

from ..doc_plugins import document
from ..plugins.command import Plugins
from . import (
    clip,
    cursors,
    delivery,
    doc_body,
    doc_threads,
    own_edits,
    own_edits_replay,
    path_presence,
    signature,
    turns,
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
    reported: doc_threads.Reported
    settled_body: str
    pending_body: str
    pending_since: float
    presence: path_presence.Presence
    plugins: Plugins
    unprojected: str | None  # the first body's text, while a plugin fails to project it
    all_threads: bool = False
    settled_quiet: float = 0  # quiet period enforced outside this detector
    latest_turn: turns.Turns | None = None  # where no hook records the writer's own edits
    seen_digest: str = ""  # the body this detector saw at its last read, and when
    seen_at: float = 0


def state_stem(state_dir: pathlib.Path, doc: pathlib.Path, me: str) -> pathlib.Path:
    return state_dir / hashlib.sha1(f"{doc.resolve()}\0{me}".encode()).hexdigest()[:16]


def _first_body(path: pathlib.Path, doc: pathlib.Path, plugins: Plugins, text: str) -> str | None:
    body = document.body(plugins, doc, text)
    if body is not None:
        cursors.write_text(path, body)
    return body


def _load_settled(
    path: pathlib.Path, doc: pathlib.Path, plugins: Plugins
) -> tuple[str, str | None]:
    """The body as of the last reported edit; the first waiter for a doc takes its current body.

    A doc that doesn't exist yet has an empty body, so writing it is reported as its creation.
    When a plugin fails on that first body, the text is returned second, still to be projected.
    """
    try:
        return path.read_text(), None
    except OSError:
        pass
    try:
        text = doc.read_text()
    except FileNotFoundError:
        text = ""
    body = _first_body(path, doc, plugins, text)
    return (text, text) if body is None else (body, None)


def _baseline_ready(w: "DocWatch") -> bool:
    """Whether the first body is projected, projecting it now if a plugin failed before."""
    if w.unprojected is None:
        return True

    body = _first_body(w.settled_path, w.doc, w.plugins, w.unprojected)
    if body is None:
        return False

    w.settled_body = w.pending_body = body
    w.unprojected = None
    return True


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
    latest_turn: turns.Turns | None = None,
    *,
    plugins: Plugins,
) -> DocWatch:
    """`writer`, when set, is the watching lemon's own_edits key: body edits it made don't wake it.

    The cursors are keyed by doc and `cursor_key`, by default `me`; a waiter using its
    lemon's own cursor directory passes "". `own_root` is where own_edits keeps the
    writer's records (default: own_edits.root()). With `latest_turn`, each body change seen
    to appear during a turn is recorded as the writer's own edit.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    own_root = own_root or own_edits.root()
    if writer and edits:
        own_edits.register(own_root, writer, doc)
    stem = state_stem(state_dir, doc, me if cursor_key is None else cursor_key)
    settled_path = stem.with_suffix(".settled.md")
    settled_body, unprojected = _load_settled(settled_path, doc, plugins) if edits else ("", None)
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
        reported=doc_threads.load(stem.with_suffix(".reported.json")),
        settled_body=settled_body,
        pending_body=settled_body,
        pending_since=0.0,
        presence=path_presence.open_watch(stem, doc, seen=bool(settled_body)),
        plugins=plugins,
        unprojected=unprojected,
        latest_turn=latest_turn,
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

    body = document.body(w.plugins, w.doc, text)
    if w.latest_turn and w.writer and body is not None:
        doc_body.observe(w, body, w.latest_turn)
    readings = document.threads(w.plugins, w.doc, text, w.mine)
    waiting = doc_threads.waiting(readings)
    new = [t for t in waiting if not doc_threads.was_reported(w.reported, t)]
    reminders = (
        [t for t in waiting if doc_threads.was_reported(w.reported, t)] if w.all_threads else []
    )
    messages = [doc_threads.message(w.doc, readings, new, reminders, len(waiting))] if new else []
    edit, consumed = (
        doc_body.changed(w, body, lambda consumed: _settle(w, body, consumed))
        if w.edits and body is not None and _baseline_ready(w)
        else ("", w.consumed)
    )
    if edit:
        messages.append(edit)
    label = f"{w.doc.name} " + ("edited" if edit and len(messages) == 1 else "comments")
    if messages and not deliver(
        delivery.Labeled("\n\n".join(clip.share(messages)), label, len(new) + bool(edit), bool(new))
    ):
        return Outcome.FAILED

    if (still := doc_threads.still_reported(w.reported, readings)) != w.reported:
        w.reported = still
        doc_threads.save(w.reported_path, still)
    if edit and body is not None:
        _settle(w, body, consumed)
    return Outcome.DELIVERED if messages else Outcome.NOTHING
