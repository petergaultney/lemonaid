"""Open each subscription's existing cursor-aware change detector."""

import time
from collections import abc
from pathlib import Path

from .. import pr_states, pr_url, watch_config
from ..config import load_config
from ..log import get_logger
from . import (
    briefs_events,
    command_cli,
    command_events,
    doc_events,
    failure_state,
    file_events,
    github_failures,
    notes,
    own_edits,
    own_pushes,
    path_presence,
    pr_activity,
    pr_events,
    pr_poller,
    pr_wait,
    repo_activity,
    repo_events,
    review_events,
    review_requests,
    roles,
    subscriptions,
)

# A new comment is reported once the file has held still this long, so a burst of
# writes from one comment arrives as one event; body edits wait the doc's full quiet period.
_THREAD_SETTLE = 3.0


_log = get_logger("watch.scouts")


def _credible_age(mtime: float) -> float:
    """Seconds since *mtime*, or 0 for a future one (clock skew), so it is timed from now."""
    return max(0.0, time.time() - mtime)


def _repo_poller(
    spec: subscriptions.Subscription,
    root: Path,
    directory: Path,
    me: str,
    deliver: abc.Callable[[str], bool],
    debounce: float,
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
                root, failed, repo, deliver, spec.interval, debounce
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


def _reviews_poller(
    spec: subscriptions.Subscription,
    root: Path,
    directory: Path,
    me: str,
    deliver: abc.Callable[[str], bool],
    debounce: float,
) -> abc.Callable[[], object]:
    scope = spec.target[1:]
    stem = review_events.state_stem(directory, scope, me)
    failed = failure_state.path(root, spec, "github")
    retry_at = 0.0

    def poll() -> None:
        nonlocal retry_at
        if time.monotonic() < retry_at:
            return

        if (prs := review_requests.fetch(scope, spec.interval)) is None:
            _log.warning("Cannot read GitHub for review requests")
            retry_at = time.monotonic() + github_failures.failed(
                root, failed, "review requests", deliver, spec.interval, debounce
            )
            return

        github_failures.recovered(root, failed)
        review_events.poll(stem, prs, deliver, spec.backlog)

    return poll


def open_poller(
    spec: subscriptions.Subscription,
    root: Path,
    writer: str,
    deliver: abc.Callable[[str], bool],
    signatures: tuple[str, ...],
    notes: notes.Reader = notes.none,
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
            fingerprint, mtime = path.read_text(), path.stat().st_mtime
        except FileNotFoundError:
            fingerprint, mtime = "", 0.0
        since = time.monotonic() - _credible_age(mtime)

        def doc() -> None:
            nonlocal fingerprint, mtime, since
            try:
                current, modified = path.read_text(), path.stat().st_mtime
            except FileNotFoundError:
                doc_events.poll(watch, deliver)
                return
            path_presence.observe(watch.presence)
            if current != fingerprint:
                # A change whose mtime did not advance (a restored file) counts from now.
                age = _credible_age(modified) if modified > mtime else 0.0
                fingerprint, since = current, time.monotonic() - age
            mtime = modified
            still_for = time.monotonic() - since
            if still_for < _THREAD_SETTLE:
                return

            watch.edits = spec.edits and still_for >= spec.quiet
            doc_events.poll(watch, deliver)

        return doc
    if spec.kind == "file":
        watch = file_events.open_watch(
            directory,
            [Path(p) for p in spec.target],
            me,
            spec.quiet,
            spec.ignore_removed,
            spec.deadline,
        )
        return lambda: file_events.poll(watch, deliver)
    if spec.kind == "command":
        pid = int(spec.target[0])
        command = command_events.open_watch(directory, pid, me)

        def exited() -> None:
            if command_events.poll(command, deliver):
                command_cli.forget(root.name, pid)

        return exited
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
            notes,
        )
        return lambda: briefs_events.poll(watch, deliver)

    settings = load_config().watch
    if spec.kind == "repo":
        return _repo_poller(spec, root, directory, me, deliver, settings.github_debounce)
    if spec.kind == "reviews":
        return _reviews_poller(spec, root, directory, me, deliver, settings.github_debounce)

    repo, number = spec.target
    stem = pr_wait.state_stem(directory, repo, int(number), me)
    trusted = watch_config.logins_on(settings.pr.trusted_commenters, pr_url.HOST)
    wake = roles.wake(spec.role or roles.AUTHOR, settings.roles)
    if writer:
        own_pushes.register(own_edits.root(), writer)
    head, retry_at = spec.head, 0.0
    reported = pr_events.reported_state(stem)
    # a mention that closed before this lemon first saw it is old news
    finished = reported == "MERGED" or (
        spec.role == roles.MENTION
        and (reported == "CLOSED" or (not reported and pr_states.is_finished(repo, number)))
    )
    failed = failure_state.path(root, spec, "github")

    def pr() -> None:
        nonlocal head, finished, retry_at
        if finished or time.monotonic() < retry_at:
            return

        pr_poller.interested(repo, int(number), root.name)
        snapshot = pr_activity.fetch(
            repo,
            int(number),
            (spec.me, *spec.legacy, *signatures),
            skip_outdated=spec.skip_outdated,
            skip_resolved=spec.skip_resolved,
            source=pr_poller.read,
        )
        if snapshot is None:
            _log.warning("Cannot read GitHub for %s#%s", repo, number)
            retry_at = time.monotonic() + github_failures.failed(
                root, failed, f"{repo}#{number}", deliver, spec.interval, settings.github_debounce
            )
            return

        github_failures.recovered(root, failed)
        pr_states.record(repo, number, snapshot.state)
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
            wake=wake,
            mentioned=spec.mentioned,
        )
        head = ""
        # a closed PR can reopen, so it is still read unless the brief only links to it
        finished = snapshot.state == "MERGED" or (
            spec.role == roles.MENTION and snapshot.state == "CLOSED"
        )

    return pr
