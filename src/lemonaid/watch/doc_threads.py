"""The comment threads waiting on a doc's watcher, and which of them it has reported.

Keys are kept by plugin, so a plugin that could not read every thread keeps the keys it
reported before: a thread that drops out of one reading is not reported again when it
returns. A thread whose key leaves a complete reading was answered or changed, and is
reported again if it waits again.
"""

import dataclasses
import json
import pathlib
from collections import abc

from ..doc_plugins import document, protocol
from . import clip, cursors

Reported = dict[str, set[str]]  # thread keys by plugin; "" holds keys saved before plugins


@dataclasses.dataclass(frozen=True)
class Waiting:
    plugin: str
    thread: protocol.Thread


def load(path: pathlib.Path) -> Reported:
    """A list, as waiters saved it before plugins, is kept under "", taken as any plugin's."""
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}

    if isinstance(saved, list):
        return {"": {str(k) for k in saved}}

    if isinstance(saved, dict):
        return {str(p): {str(k) for k in ks} for p, ks in saved.items() if isinstance(ks, list)}

    return {}


def save(path: pathlib.Path, reported: Reported) -> None:
    cursors.write_json(path, {p: sorted(ks) for p, ks in sorted(reported.items())})


def waiting(readings: abc.Iterable[document.PluginReading]) -> list[Waiting]:
    return [Waiting(r.plugin, t) for r in readings for t in r.reading.threads if t.waiting]


def was_reported(reported: Reported, w: Waiting) -> bool:
    return w.thread.key in reported.get(w.plugin, set()) or w.thread.key in reported.get("", set())


def still_reported(reported: Reported, readings: abc.Sequence[document.PluginReading]) -> Reported:
    kept = {
        r.plugin: {t.key for t in r.reading.threads if t.waiting}
        | (set() if r.reading.complete else reported.get(r.plugin, set()))
        for r in readings
    }
    if "" in reported and not all(r.reading.complete for r in readings):
        kept[""] = reported[""]
    return {p: ks for p, ks in kept.items() if ks}


def message(
    doc: pathlib.Path,
    readings: abc.Sequence[document.PluginReading],
    new: abc.Sequence[Waiting],
    reminders: abc.Sequence[Waiting],
    total: int,
) -> str:
    """The wake for *new* threads. A plugin's notes come first, so a wake cut to the batch
    limit still says how to answer."""
    notes = [n for r in readings if any(w.plugin == r.plugin for w in new) for n in r.reading.notes]
    return clip.shorten(
        f"{len(new)} new or changed unanswered thread(s) in {doc} ({total} unanswered in all)\n\n"
        + "".join(f"{n}\n" for n in notes)
        + ("\n" if notes else "")
        + "\n\n".join(w.thread.text for w in new)
        + "".join(f"\n\nStill unanswered, already reported: {w.thread.gist}" for w in reminders),
        clip.BATCH_LIMIT,
    )
