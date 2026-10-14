"""A cancellable thread per subscription. Cursors advance only after batch delivery."""

import dataclasses
import queue
import threading
from pathlib import Path

from ..log import get_logger
from . import delivery, doc_version, failure_state, own_edits, scout_pollers, subscriptions

_log = get_logger("watch.scouts")


@dataclasses.dataclass
class Pending:
    source: str
    message: str
    owner: "Scout | None" = None
    doc_version: int = 0
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
    ):
        self.spec, self.root, self.writer = spec, root, writer
        self.output, self.signatures = output, signatures
        self.stopped = threading.Event()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def deliver(self, message: str) -> bool:
        version = doc_version.of(Path(self.spec.target[0])) if self.spec.kind == "doc" else 0
        pending = Pending(self.spec.source, message, self, version)
        self.output.put(pending)
        while not pending.acknowledged.wait(0.1):
            if self.stopped.is_set():
                raise delivery.Failed("Batch was not delivered")
        if not pending.delivered:
            raise delivery.Failed("Batch was not delivered")
        return True

    def run(self) -> None:
        poll = None
        failed = failure_state.path(self.root, self.spec, "error")
        try:
            while not self.stopped.is_set():
                try:
                    poll = poll or scout_pollers.open_poller(
                        self.spec, self.root, self.writer, self.deliver, self.signatures
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
                if self.stopped.wait(max(0.05, self.spec.interval)):
                    break
        finally:
            self.ready.set()
            if self.spec.kind == "doc" and self.spec.edits and self.writer:
                own_edits.unregister(own_edits.root(), self.writer, Path(self.spec.target[0]))

    def stop(self) -> None:
        self.stopped.set()
