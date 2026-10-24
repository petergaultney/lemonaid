"""The grove's quit keys: `q` closes it, `Q` ends the process that hosts it."""

import enum

from . import keys


class Quit(enum.Enum):
    NO = enum.auto()
    CLOSE = enum.auto()
    PROCESS = enum.auto()


def quit_for(where: keys.Where, key: str) -> Quit:
    if where.search is not None:
        return Quit.NO

    return {"q": Quit.CLOSE, "Q": Quit.PROCESS}.get(key, Quit.NO)
