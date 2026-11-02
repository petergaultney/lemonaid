"""One inspector pass end to end, for `task inspect` and the scout host alike: judge every
subject, then send the challenges that are due. Only one pass runs at a time, so two can't
both send a challenge before either records it as sent."""

import contextlib
import fcntl
import time
import typing as ty
from collections import abc

from ...inbox import db
from ...tasks_config import TasksConfig
from ..briefs import session
from ..checker.session import Ask
from . import cases, challenges, inspector, live, memory


class Done(ty.NamedTuple):
    judged: inspector.Pass
    sent: list[str]
    open: list[dict[str, ty.Any]]


@contextlib.contextmanager
def sole() -> abc.Iterator[bool]:
    """Whether this process may run a pass now."""
    state = live.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "task-inspector.lock", "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return

        yield True


def run(config: TasksConfig, ask: Ask, send: bool, remembered: memory.Memory | None = None) -> Done:
    """With *send* false, the challenges due are listed but not sent."""
    with db.connect() as conn:
        session.caught_up(conn)
        judged = inspector.run(conn, time.time(), ask, config.policy, remembered=remembered)
        sent = challenges.deliver(
            conn,
            config.challenge_interval if send else 0,
            config.max_challenge_interval,
            config.opt_out.keys(),
            time.time(),
        )
        return Done(judged, sent, cases.open_cases(conn))
