"""Open each subscription's existing cursor-aware change detector."""

import time
from collections import abc
from pathlib import Path

from .. import pr_url, watch_config
from ..config import load_config
from ..log import get_logger
from . import (
    briefs_events,
    doc_events,
    failure_state,
    file_events,
    github_failures,
    own_edits,
    own_pushes,
    path_presence,
    pr_activity,
    pr_events,
    pr_wait,
    repo_activity,
    repo_events,
    subscriptions,
)

# A new comment is reported once the file has held still this long, so a burst of
# writes from one comment arrives as one event; body edits wait the doc's full quiet period.
_THREAD_SETTLE = 3.0

_log = get_logger("watch.scouts")


def _repo_poller(
    spec: subscriptions.Subscription,
    root: Path,
    directory: Path,
    me: str,
    deliver: abc.Callable[[str], bool],
) -> abc.Callable[[], object]:
    [repo] = spec.target
    stem = repo_events.state_stem(directory, repo, me)
    failed = failure_state.path(root, spec, "github")
    retry_at = 0.0

    def poll() -> None:
        nonlocal retry_at
        if time.monotonic() < retry_at:
            return

        if (prs := repo_activity.fetch(repo)) is None:
            _log.warning("Cannot read GitHub for %s", repo)
            retry_at = time.monotonic() + github_failures.failed(
                root, failed, repo, deliver, spec.interval
            )
            return

        github_failures.recovered(root, failed)
        repo_events.poll(
            stem,
            repo,
            prs,
            deliver,
            labels=spec.labels,
            exclude_authors=spec.exclude_authors,
            pushes=spec.pushes,
        )

    return poll


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
                doc_events.poll(watch, deliver)
                return
            path_presence.observe(watch.presence)
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
            directory,
            spec.target[0],
            me,
            spec.quiet,
            spec.to,
            spec.orphans,
            spec.lemons,
            spec.needs,
        )
        return lambda: briefs_events.poll(watch, deliver)

    if spec.kind == "repo":
        return _repo_poller(spec, root, directory, me, deliver)

    repo, number = spec.target
    stem = pr_wait.state_stem(directory, repo, int(number), me)
    trusted = watch_config.logins_on(load_config().watch.pr.trusted_commenters, pr_url.HOST)
    if writer:
        own_pushes.register(own_edits.root(), writer)
    head, closed, retry_at = spec.head, False, 0.0
    failed = failure_state.path(root, spec, "github")

    def pr() -> None:
        nonlocal head, closed, retry_at
        if closed or time.monotonic() < retry_at:
            return

        snapshot = pr_activity.fetch(
            repo,
            int(number),
            (spec.me, *spec.legacy, *signatures),
            skip_outdated=spec.skip_outdated,
            skip_resolved=spec.skip_resolved,
        )
        if snapshot is None:
            _log.warning("Cannot read GitHub for %s#%s", repo, number)
            retry_at = time.monotonic() + github_failures.failed(
                root, failed, f"{repo}#{number}", deliver, spec.interval
            )
            return

        github_failures.recovered(root, failed)
        pr_events.poll(
            stem,
            int(number),
            snapshot,
            deliver,
            head=head if not stem.with_suffix(".head.json").exists() else "",
            comments=spec.comments,
            ci=spec.ci,
            own_head=lambda value: own_pushes.is_own(own_edits.root(), writer, value),
            trusted=trusted,
        )
        head = ""
        closed = snapshot.state != "OPEN"

    return pr
