"""What `lemonaid brief status --help` and `lemonaid brief statuses` tell a lemon about
choosing a status, from the configured statuses."""

import textwrap
from collections import abc

from .. import status_registry

_INTRO = """\
A status says you wait on a person or a process. Leave it out when the next move is yours
or another lemon's: hand that lemon your task (`task assign`) or wait for its task
(`task depend`), and give your task its PR while CI runs (`task set-url`). The inbox then
shows whether you are active, idle, deaf or dead. `done` ends the work.
"""

_OUTRO = """\
Several lemons waiting on the same move from the user: only the one that owns it sets the
status; the others set none and name it under `### Waiting on`. Put the reason in `## Now`,
never on the `Status:` line. `lemonaid brief statuses` lists these with their properties.
"""


def table(statuses: abc.Iterable[status_registry.Status]) -> str:
    """Each status and when to use it, one per paragraph."""
    width = max((len(s.name) for s in statuses), default=0) + 2
    return "\n".join(
        textwrap.fill(
            s.description,
            90,
            initial_indent=f"  {s.name.ljust(width)}",
            subsequent_indent=" " * (width + 2),
        )
        for s in statuses
    )


def guide(statuses: abc.Sequence[status_registry.Status]) -> str:
    return f"{_INTRO}\n{table(statuses)}\n\n{_OUTRO}"
