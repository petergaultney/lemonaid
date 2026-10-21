"""Reread subscriptions while waiting and deliver every pending source in one wake."""

import queue
import time
from collections import abc
from pathlib import Path

from ..config import load_config
from ..messages import store
from . import delivery, doc_version, notes, scouts, subscription_state


def _messages(inbox: Path) -> list[tuple[Path, str]]:
    return [
        (path, path.read_text())
        for path in sorted(inbox.glob("*.md"))
        if path.is_file() and not path.is_symlink()
    ]


def _reconcile(
    running: dict[tuple, scouts.Scout],
    specs: dict,
    pending: list[scouts.Pending],
    root: Path,
    writer: str,
    output: "queue.Queue[scouts.Pending]",
    signatures: tuple[str, ...],
    notes: notes.Reader,
) -> list[scouts.Pending]:
    for key in list(running):
        if key not in specs or running[key].spec != specs[key]:
            retired = running.pop(key)
            retired.stop()
            retired.thread.join(timeout=1)
            pending = [p for p in pending if p.source != retired.spec.source]
    for key, spec in specs.items():
        if key not in running:
            scout = scouts.Scout(spec, root, writer, output, signatures, notes)
            running[key] = scout
            scout.thread.start()
    return pending


def _collect(
    output: "queue.Queue[scouts.Pending]",
    running: dict[tuple, scouts.Scout],
    pending: list[scouts.Pending],
) -> bool:
    arrived = False
    while True:
        try:
            event = output.get_nowait()
        except queue.Empty:
            break
        if event.owner and running.get(event.owner.spec.key) is not event.owner:
            event.acknowledged.set()
            continue

        pending.append(event)
        arrived = True
    for event in list(pending):
        if (
            event.owner
            and event.owner.spec.kind == "doc"
            and doc_version.of(Path(event.owner.spec.target[0])) != event.doc_version
        ):
            event.owner.stop()
            event.acknowledged.set()
            event.owner.thread.join(timeout=1)
            running.pop(event.owner.spec.key, None)
            pending.remove(event)
    return arrived


def wait(
    path: Path,
    inbox: Path,
    root: Path,
    writer: str,
    deliver: delivery.Deliver,
    still_attached: abc.Callable[[], bool],
    *,
    interval: float = 0.5,
    quiet: float = 2,
    notes: notes.Reader = notes.none,
) -> None:
    vaults = tuple(load_config().brief.vaults)
    output: queue.Queue[scouts.Pending] = queue.Queue()
    running: dict[tuple, scouts.Scout] = {}
    pending: list[scouts.Pending] = []
    since, last_messages = 0.0, ()
    try:
        while still_attached():
            listed, problem = subscription_state.read(path, root, Path.cwd(), inbox.name, vaults)
            specs = {s.key: s for s in listed}
            if not problem:
                pending = [p for p in pending if p.source != "brief"]
            elif not any(p.message == problem for p in pending):
                pending = [p for p in pending if p.source != "brief"]
                pending.append(scouts.Pending("brief", problem))
                since = time.monotonic()
            wordy = inbox.name.rsplit(".", 1)[-1]
            signatures = tuple(
                f"{role} ({wordy})" for role in ("Author", "Reviewer", "Parent", "Lead")
            )
            pending = _reconcile(running, specs, pending, root, writer, output, signatures, notes)
            if _collect(output, running, pending):
                since = time.monotonic()
            with store.receive_lock(inbox, wait=False) as held:
                messages = _messages(inbox) if held else []
                names = tuple(p.name for p, _ in messages)
                if names != last_messages:
                    last_messages, since = names, time.monotonic()
                armed = all(
                    s.ready.is_set() or any(p.source == s.spec.source for p in pending)
                    for s in running.values()
                )
                if (pending or messages) and armed and time.monotonic() - since >= quiet:
                    deliver(
                        "\n\n".join(
                            [
                                *(f"[{p.source}] {p.message}" for p in pending),
                                *(f"[inbox] {body.rstrip()}" for _, body in messages),
                            ]
                        )
                    )
                    for message, _ in messages:
                        store.mark_done(message)
                    for event in pending:
                        if event.source == "brief":
                            subscription_state.remember(root, event.message)
                        event.delivered = True
                        event.acknowledged.set()
                    # Let detectors finish writing their delivered cursors before releasing the waiter.
                    for scout in running.values():
                        scout.stop()
                    deadline = time.monotonic() + 35
                    for scout in running.values():
                        scout.thread.join(timeout=max(0, deadline - time.monotonic()))
                    return
            time.sleep(interval)
    finally:
        for scout in running.values():
            scout.stop()
        for event in pending:
            event.acknowledged.set()
        deadline = time.monotonic() + 1
        for scout in running.values():
            scout.thread.join(timeout=max(0, deadline - time.monotonic()))
