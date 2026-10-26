"""The key that flips a zoomed block's lemon lists to their other page.

A terminal under tmux never reports a key's release, so a held key is known by its repeats: the
lists flip on the first press and flip back once the repeats stop.
"""

import dataclasses

from ...config import Config

# A held key starts repeating after macOS's default delay of up to half a second, then repeats
# about every 0.1 seconds; the waits leave room for a redraw that holds up a repeat on its way in.
FIRST_WAIT = 0.6
REPEAT_WAIT = 0.3


@dataclasses.dataclass(frozen=True)
class Flip:
    key: str = ";"
    hold: bool = True  # shown while the key is held; otherwise until it is pressed again


DEFAULT = Flip()


def pressed(flipped: bool, hold: bool) -> tuple[bool, float]:
    """The page after a press, and the seconds until it flips back: 0 for never."""
    if not hold:
        return not flipped, 0.0

    return True, REPEAT_WAIT if flipped else FIRST_WAIT


def configured(config: Config) -> Flip:
    return Flip(config.tui.grove_flip_key, config.tui.grove_flip == "hold")
