"""Follow one watch-source subscription for one lemon: poll its plugin from the lemon's cursor
and deliver what it reports (docs/source-plugins.md).

A poll happens at once, whenever the plugin says the subscription is `ready`, and after the
`every` its last answer gave. The cursor advances only after delivery. A `problem` reaches the
lemon once per lapse (`sources.problems`). An `end` is delivered once, and the subscription's
lines leave the brief's `## Watching`.
"""

import shlex
import threading
import time
import uuid
from collections import abc
from pathlib import Path

from ..brief import lemon, verbs_cli, waiters
from ..inbox import db
from ..log import get_logger
from ..plugins import processes, running
from ..sources import answer, host, plugin
from . import cursors, delivery

_IDLE = 3600.0  # seconds between polls when the plugin gives no `every`

_log = get_logger("watch.source_events")


def state_path(directory: Path, target: abc.Sequence[str]) -> Path:
    return directory / f"{'-'.join(target)}.json"


def follows(command: str, source: plugin.Source, target: tuple[str, ...]) -> bool:
    """Whether a `## Watching` command follows *target* from *source*, however it names it."""
    try:
        words = shlex.split(command)
    except ValueError:
        return False

    if words[:3] != ["lemonaid", "watch", source.name]:
        return False

    try:
        return host.check(source, plugin.words(words[3:]).args) == target
    except running.Failed:
        return False


def _forget(lemon_id: str, source: plugin.Source, target: tuple[str, ...]) -> None:
    """Remove every line for *target* from *lemon_id*'s brief, if any."""
    with db.connect() as conn:
        path = lemon.brief_of(conn, lemon_id) if lemon_id else None
    if path is None or not path.is_file():
        return

    if error := verbs_cli.edit(
        path,
        lambda text: waiters.remove_where(text, lambda command: follows(command, source, target)),
        preserve_existing=True,
    ):
        _log.warning("could not stop following %s in %s: %s", target, path, error)


class Poller:
    """Called once per scout tick; polls the plugin only when it is due."""

    def __init__(
        self,
        source: plugin.Source,
        args: tuple[str, ...],
        target: tuple[str, ...],
        brief_done: bool,
        directory: Path,
        lemon_id: str,
        deliver: abc.Callable[[str], object],
        warn: abc.Callable[[str], object],
        recovered: abc.Callable[[], object] = lambda: None,
    ) -> None:
        """*directory* holds the lemon's cursors for *source*. *warn* gets each `problem`, and
        *recovered* is called after each poll that read the source."""
        self.source, self.args, self.target = source, args, target
        self.brief_done, self.lemon_id = brief_done, lemon_id
        self.deliver, self.warn, self.recovered = deliver, warn, recovered
        self.path = state_path(directory, target)
        self.follower = lemon_id or directory.parent.name
        self.key = uuid.uuid4().hex
        self.next_at = 0.0
        self.launch = host.launch(source)
        self.generation = processes.generation(self.launch)  # of the process that knows the key
        self.ended = False

    def wake_with(self, wake: threading.Event) -> None:
        """Set *wake* when the plugin says this subscription is ready, or fails."""
        host.listen(self.key, self.launch, wake)

    def _end(self, said: answer.Said) -> None:
        self.ended = True
        self.deliver(
            delivery.Labeled(
                f"{said.text}; its line left ## Watching",
                said.label or f"stopped following a {self.source.name} subscription",
            )
        )
        _forget(self.lemon_id, self.source, self.target)
        self.path.unlink(missing_ok=True)
        self.close()

    def _ask(self) -> answer.Answer | None:
        try:
            cursor = self.path.read_text()
        except FileNotFoundError:
            cursor = ""
        fields = [
            *(("arg", a) for a in self.args),
            ("follower", self.follower),
            *((("done", "yes"),) if self.brief_done else ()),
        ]
        try:
            return answer.parse(processes.ask(self.launch, f"poll {self.key}", fields, cursor))
        except running.Failed as error:
            _log.warning("cannot poll %s %s: %s", self.source.name, self.target, error)
            return None

    def __call__(self) -> None:
        if self.ended:
            return

        now = time.monotonic()
        replaced = processes.generation(self.launch) != self.generation and processes.may_start(
            self.launch
        )
        if not (host.take_ready(self.key) or now >= self.next_at or replaced):
            return

        generation = processes.generation(self.launch)
        found = self._ask()
        if found is None:
            self.next_at = now + processes.RETRY_AFTER
            return

        self.generation = generation

        self.next_at = now + (found.every or _IDLE)
        if found.problem:
            said = found.problem
            self.warn(delivery.Labeled(said.text, said.label or f"{self.source.name} problem"))
        if found.cursor is not None:
            self.recovered()
        if found.wake:
            said = found.wake
            self.deliver(delivery.Labeled(said.text, said.label, said.count, True))
        if found.cursor is not None:
            cursors.write_text(self.path, found.cursor)
        if found.end:
            self._end(found.end)

    def close(self) -> None:
        """Tell the plugin this subscription is gone, so it stops following it."""
        host.unlisten(self.key)
        try:
            processes.ask(self.launch, f"forget {self.key}", [], "")
        except running.Failed as error:
            _log.info("could not tell %s to forget %s: %s", self.source.name, self.target, error)
