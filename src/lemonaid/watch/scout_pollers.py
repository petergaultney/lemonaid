"""Open each subscription's existing cursor-aware change detector."""

import subprocess
import time
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import (
    briefs_events,
    doc_events,
    failure_state,
    file_events,
    own_edits,
    own_pushes,
    pr_activity,
    pr_events,
    pr_wait,
    subscriptions,
)

# A new comment is reported once the file has held still this long, so a burst of
# writes from one comment arrives as one event; body edits wait the doc's full quiet period.
_THREAD_SETTLE = 3.0

_log = get_logger("watch.scouts")


def open_poller(
    spec: subscriptions.Subscription,
    root: Path,
    writer: str,
    deliver: abc.Callable[[str], bool],
    signatures: tuple[str, ...],
) -> abc.Callable[[], object]:
    directory = spec.state_dir or root / spec.kind
    directory.mkdir(parents=True, exist_ok=True)
    me = spec.me if spec.state_dir else ""
    if spec.kind == "doc":
        path = Path(spec.target[0])
        watch = doc_events.open_watch(
            directory,
            path,
            spec.me,
            (*spec.legacy, *signatures),
            spec.edits,
            0,
            writer,
            cursor_key=me,
        )
        watch.all_threads = True
        watch.settled_quiet = spec.quiet
        try:
            fingerprint = path.read_text()
            age = max(0, time.time() - path.stat().st_mtime)
        except FileNotFoundError:
            fingerprint, age = "", spec.quiet
        since = time.monotonic() - age

        def doc() -> None:
            nonlocal fingerprint, since
            try:
                current = path.read_text()
            except FileNotFoundError:
                return
            if current != fingerprint:
                fingerprint, since = current, time.monotonic()
            still_for = time.monotonic() - since
            if still_for < _THREAD_SETTLE:
                return

            watch.edits = spec.edits and still_for >= spec.quiet
            doc_events.poll(watch, deliver)

        return doc
    if spec.kind == "file":
        watch = file_events.open_watch(
            directory, [Path(p) for p in spec.target], me, spec.quiet, spec.ignore_removed
        )
        return lambda: file_events.poll(watch, deliver)
    if spec.kind == "briefs":
        watch = briefs_events.open_watch(
            directory, spec.target[0], me, spec.quiet, spec.to, spec.orphans
        )
        return lambda: briefs_events.poll(watch, deliver)

    repo, number = spec.target
    stem = pr_wait.state_stem(directory, repo, int(number), me)
    if writer:
        own_pushes.register(own_edits.root(), writer)
    head, closed = spec.head, False
    failed = failure_state.path(root, spec, "github")

    def pr() -> None:
        nonlocal head, closed
        if closed:
            return
        try:
            snapshot = pr_activity.fetch(
                repo,
                int(number),
                (spec.me, *spec.legacy, *signatures),
                skip_outdated=spec.skip_outdated,
                skip_resolved=spec.skip_resolved,
            )
        except subprocess.TimeoutExpired:
            snapshot = None
        if snapshot is None:
            _log.warning("Cannot reach GitHub for %s#%s", repo, number)
            failure_state.report(
                failed,
                f"Cannot reach GitHub for {repo}#{number} after repeated attempts",
                deliver,
                threshold=3,
            )
            return
        failure_state.clear(failed)
        pr_events.poll(
            stem,
            int(number),
            snapshot,
            deliver,
            head=head if not stem.with_suffix(".head.json").exists() else "",
            comments=spec.comments,
            ci=spec.ci,
            own_head=lambda value: own_pushes.is_own(own_edits.root(), writer, value),
        )
        head = ""
        closed = snapshot.state != "OPEN"

    return pr
