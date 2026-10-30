"""A cancellable thread per subscription. Cursors advance only after batch delivery."""

import dataclasses
import os
import queue
import threading
import time
import typing as ty
from pathlib import Path

from ..log import get_logger
from . import (
    briefs_events,
    delivery,
    doc_version,
    failure_state,
    notes,
    own_edits,
    scout_pollers,
    subscriptions,
    waits,
)

_log = get_logger("watch.scouts")

_SETTLE = (
    5.0  # after a change, poll at the subscription's own interval this much past its quiet period
)


class _Sources(ty.NamedTuple):
    paths: list[Path]
    contents: list[Path]  # directories whose files' contents the detector reads


def _sources(spec: subscriptions.Subscription) -> _Sources:
    """What a subscription's detector reads from disk; PR and repo detectors read GitHub."""
    if spec.kind in ("doc", "file"):
        targets = [Path(target) for target in spec.target]
        return _Sources([t for t in targets if not t.is_dir()], [t for t in targets if t.is_dir()])

    if spec.kind == "briefs":
        return _Sources(briefs_events.brief_paths(spec.target[0], spec.lemons, spec.orphans), [])

    return _Sources([], [])


def _stat(path: Path | str) -> tuple[int, int] | None:
    try:
        found = os.stat(path)
    except OSError:
        return None

    return found.st_mtime_ns, found.st_size


def _listing(directory: Path) -> list[tuple[str, tuple[int, int] | None]]:
    try:
        with os.scandir(directory) as entries:
            return sorted((e.name, _stat(e.path)) for e in entries if e.is_file())
    except OSError:
        return []


def _stamp(sources: _Sources) -> tuple:
    """Changes whenever a source does, so a poll that finds a change without an event settles it."""
    return (
        tuple(_stat(path) for path in sources.paths),
        tuple((_stat(d), tuple(_listing(d))) for d in sources.contents),
    )


@dataclasses.dataclass
class Pending:
    source: str
    message: str
    owner: "Scout | None" = None
    doc_version: int = 0
    detected: float = dataclasses.field(default_factory=time.time)
    acknowledged: threading.Event = dataclasses.field(default_factory=threading.Event)
    delivered: bool = False


class Scout:
    def __init__(
        self,
        spec: subscriptions.Subscription,
        root: Path,
        writer: str,
        output: "queue.Queue[Pending]",
        signatures: tuple[str, ...],
        notes: notes.Reader,
        pacing: waits.Waits = waits.TIMERS,
        detected: threading.Event | None = None,
    ):
        self.spec, self.root, self.writer = spec, root, writer
        self.output, self.signatures, self.notes = output, signatures, notes
        self.pacing, self.detected = (
            pacing,
            detected or threading.Event(),
        )  # detected wakes the batch
        self.stopped = threading.Event()
        self.wake = threading.Event()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def deliver(self, message: str) -> bool:
        version = doc_version.of(Path(self.spec.target[0])) if self.spec.kind == "doc" else 0
        pending = Pending(self.spec.source, message, self, version)
        self.output.put(pending)
        self.detected.set()
        while not pending.acknowledged.wait(0.1):
            if self.stopped.is_set():
                raise delivery.Failed("Batch was not delivered")
        if not pending.delivered:
            raise delivery.Failed("Batch was not delivered")
        return True

    def run(self) -> None:
        poll = None
        failed = failure_state.path(self.root, self.spec, "error")
        sources = _sources(self.spec)
        unwatch = self.pacing.watch(sources.paths, (), self.wake, sources.contents)
        stamp: tuple | None = _stamp(sources)
        active_until = (
            time.monotonic() + self.spec.quiet + _SETTLE
        )  # a change just before start settles
        try:
            while not self.stopped.is_set():
                try:
                    poll = poll or scout_pollers.open_poller(
                        self.spec, self.root, self.writer, self.deliver, self.signatures, self.notes
                    )
                    poll()
                    failure_state.clear(failed)
                except delivery.Failed:
                    break
                except (OSError, ValueError, RuntimeError) as error:
                    _log.exception("Subscription failed: %s", self.spec.target)
                    if not self.stopped.is_set():
                        try:
                            failure_state.report(
                                failed, f"Subscription failed: {error}", self.deliver
                            )
                        except delivery.Failed:
                            break
                self.ready.set()
                if self.spec.kind == "briefs" and (current := _sources(self.spec)) != sources:
                    unwatch()  # a child linked or unlinked, or a watched lemon added
                    sources, stamp = current, None
                    unwatch = self.pacing.watch(sources.paths, (), self.wake, sources.contents)
                if (latest := _stamp(sources)) != stamp:
                    stamp, active_until = latest, time.monotonic() + self.spec.quiet + _SETTLE
                busy = time.monotonic() < active_until
                if self.wake.wait(
                    waits.sleep_for(self.pacing, max(0.05, self.spec.interval), busy)
                ):
                    active_until = time.monotonic() + self.spec.quiet + _SETTLE
                self.wake.clear()
        finally:
            unwatch()
            self.ready.set()
            if self.spec.kind == "doc" and self.spec.edits and self.writer:
                own_edits.unregister(own_edits.root(), self.writer, Path(self.spec.target[0]))

    def stop(self) -> None:
        self.stopped.set()
        self.wake.set()
