"""The daily idle sweep as a scout host service.

One host runs per lemonaid home, so one process decides when the sweep runs, in the
environment the host started with. A command or harness hook run anywhere else never
starts it.
"""

import dataclasses
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from ..audit import actor
from ..config import load_config
from ..log import LOG_PATH, get_logger
from ..watch import host_services, reconcile, registry

_log = get_logger("brief.sweep_service")
_DAILY_SECONDS = 24 * 60 * 60
_CHECK_SECONDS = 10 * 60


@dataclasses.dataclass
class _State:
    checked: float = -float("inf")  # monotonic time of the last check


def _stamp() -> Path:
    return registry.root() / "brief-archive-sweep"


def start_due() -> None:
    """Start a background sweep under `[brief] archive_idle_days`, at most once a day."""
    config = load_config().brief
    try:
        if not config.archive_idle_days or time.time() - _stamp().stat().st_mtime < _DAILY_SECONDS:
            return
    except FileNotFoundError:
        pass
    if reconcile.editable_install():
        return

    _stamp().parent.mkdir(parents=True, exist_ok=True)
    _stamp().touch()
    try:
        with LOG_PATH.open("a") as log:
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "lemonaid",
                    "brief",
                    "archive",
                    "--idle-days",
                    str(config.archive_idle_days),
                    "--max",
                    str(config.archive_sweep_max),
                ],
                env={
                    **{k: v for k, v in os.environ.items() if k != "CODEX_THREAD_ID"},
                    actor.ACTOR_ENV: "idle sweep",
                },
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
    except OSError as error:
        _log.warning("could not start the brief archive sweep: %s", error)


def tick(state: _State, quitting: threading.Event) -> int:
    """Start the sweep once a day has passed; 0, since the sweep keeps no host up by itself."""
    if quitting.is_set() or time.monotonic() - state.checked < _CHECK_SECONDS:
        return 0

    state.checked = time.monotonic()
    start_due()
    return 0


def service() -> host_services.Service:
    state = _State()
    return host_services.Service(
        lambda quitting: tick(state, quitting), lambda: None, lambda: False
    )
