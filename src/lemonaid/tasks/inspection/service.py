"""The task inspector as a scout host service: a pass every `[tasks] inspect_interval`
seconds, on its own thread, asking one long-running checker process.

It remembers what the checker judged, so a pass in which nothing changed asks it nothing.
It reads the config again only when the file changes, and stops its checker when the
interval goes back to 0. It never keeps the host up by itself: the host runs while lemons
do, and with none there is nothing to inspect.
"""

import dataclasses
import threading
import time

from ...config import get_config_path, load_config
from ...log import get_logger
from ...tasks_config import TasksConfig
from ...watch import host_services
from ..checker import replay, session
from . import memory, passes

_log = get_logger("tasks.inspection.service")


@dataclasses.dataclass
class _State:
    config: TasksConfig = dataclasses.field(default_factory=TasksConfig)
    config_seen: tuple[int, int] | None = None  # the file's mtime and size when last read
    checker: session.Session | None = None
    checker_argv: tuple[tuple[str, ...], float] = ((), 0.0)
    remembered: memory.Memory = dataclasses.field(default_factory=memory.new)
    started: float = -float("inf")  # monotonic time of the last pass
    worker: threading.Thread | None = None


def _config(state: _State) -> TasksConfig:
    path = get_config_path()
    try:
        stat = path.stat()
        seen = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        seen = None
    if seen != state.config_seen:
        state.config, state.config_seen = load_config(path).tasks, seen
    return state.config


def _stop(state: _State) -> None:
    if state.checker is not None:
        state.checker.close()
    state.checker = None


def _pass(config: TasksConfig, checker: session.Session, remembered: memory.Memory) -> None:
    try:
        with passes.sole() as mine:
            if not mine:
                return

            done = passes.run(config, checker.ask, send=True, remembered=remembered)
    except Exception:  # the host outlives any one pass
        _log.exception("Task inspector pass failed")
        return

    _log.info(
        "Task inspector pass: %d tasks, %d cases opened, %d sent, %d checker failures",
        done.judged.evaluated,
        len(done.judged.opened),
        len(done.sent),
        len(done.judged.failures),
    )


def tick(state: _State, quitting: threading.Event) -> int:
    """Start a pass when one is due; 0, since the inspector keeps no host up by itself."""
    if state.worker is not None and state.worker.is_alive():
        return 0

    config = _config(state)
    interval = config.inspect_interval if config.enabled else 0
    if not interval or quitting.is_set():
        _stop(state)
        return 0

    wanted = (config.checker or tuple(replay.DEFAULT_CHECKER), config.checker_timeout)
    if state.checker is None or wanted != state.checker_argv:
        _stop(state)
        state.checker, state.checker_argv = session.Session(*wanted), wanted
        state.remembered = memory.new()  # another checker may judge differently
    if time.monotonic() - state.started < interval:
        return 0

    state.started = time.monotonic()
    state.worker = threading.Thread(
        target=_pass,
        args=(config, state.checker, state.remembered),
        name="task-inspector",
        daemon=True,
    )
    state.worker.start()
    return 0


def service() -> host_services.Service:
    state = _State()

    def join() -> None:
        if state.worker is not None:
            state.worker.join(timeout=30)
        _stop(state)

    return host_services.Service(lambda quitting: tick(state, quitting), join, lambda: False)
