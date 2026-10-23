"""The grove as a fast tmux popup: the module `lemonaid tmux popup grove` finds by its name.

See `lemonaid.tmux.popup_resident` for what `run` is asked to do.
"""

from collections import abc

from .source import popup

TITLE = " lemon grove "
# A pane smaller than this, such as the inbox's sidebar or top strip, is the wrong shape for a map.
MAP_WIDTH, MAP_HEIGHT = 150, 40


def wants_popup(width: int, height: int) -> bool:
    return width < MAP_WIDTH or height < MAP_HEIGHT


def run(
    opener: abc.Callable[[], str],
    rename_session: abc.Callable[[str, str], str],
    hide: abc.Callable[[], None],
) -> None:
    popup.run(opener, rename_session, hide)
