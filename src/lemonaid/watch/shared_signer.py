"""Whether a doc waiter's `--me` is a name more than one active lemon signs with.

Such a waiter takes replies signed by any of them as its own, so it would sleep
through the other lemon's answers.
"""

from ..brief import active_names
from ..inbox import db
from . import signature


def warning(me: str) -> str:
    """The warning for a waiter signing as *me*, or "" when the name is one lemon's."""
    name = parsed[0] if (parsed := signature.parse(me)) else me.strip()
    with db.connect() as conn:
        holders = sorted(active_names.holding(conn, name))
    if len(holders) < 2:
        return ""

    return (
        f"warning: {name} is the name of {', '.join(holders)}, so this waiter takes"
        f" replies signed {name} by any of them as its own. Give all but one a new name"
        " with `lemonaid brief id --reroll`."
    )
