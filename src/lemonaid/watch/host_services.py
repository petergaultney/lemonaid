"""Work besides push scouts that the scout host runs, so it can share the host's interpreter.

The host's callers pass services in (see `cli.py`), which keeps `watch` from depending on
what they do.
"""

import threading
import typing as ty
from collections import abc


class Service(ty.NamedTuple):
    tick: abc.Callable[[threading.Event], int]  # catch up; how much work it has, 0 for none
    join: abc.Callable[[], None]  # after the host's quitting event is set
    pending: abc.Callable[
        [], bool
    ]  # work registered since its last tick, checked as the host exits


Factory = abc.Callable[[], Service]
