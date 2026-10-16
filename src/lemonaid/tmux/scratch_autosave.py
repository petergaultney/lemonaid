"""Settled scratch geometry, sampled by the managed inbox's single timer."""

import os
import time
from dataclasses import dataclass

from . import command, follow, scratch

_EPOCH = "@lemonaid_scratch_geometry_epoch"
_SETTLE_SECONDS = 0.75


def install_guards() -> None:
    increment = f"set-option -gF {_EPOCH} '#{{e|+|:#{{?{_EPOCH},#{{{_EPOCH}}},0}},1}}'"
    hooks = (
        *follow.HOOKS,
        "window-resized",
        "after-select-layout",
    )
    args: list[str] = []
    for hook in hooks:
        args += ["set-hook", "-g", f"{hook}[101]", increment, ";"]
    args += [
        "set-hook",
        "-g",
        "after-resize-pane[101]",
        f"if-shell -F '#{{window_zoomed_flag}}' \"{increment}\"",
    ]
    command.run(args, check=True)


@dataclass(frozen=True)
class _Sample:
    context: tuple[str, ...]
    position: str
    size: int
    expected: int


def _sample(pane: str) -> _Sample | None:
    fields = (
        "pane_id",
        follow.MARKER_OPTION,
        follow.PANE_OPTION,
        follow.FOLLOW_OPTION,
        follow.POSITION_OPTION,
        "session_name",
        "window_id",
        "window_zoomed_flag",
        "window_width",
        "window_height",
        "pane_width",
        "pane_height",
        follow.WIDTH_OPTION,
        follow.HEIGHT_OPTION,
        _EPOCH,
        "P:#{pane_id}/",
    )
    result = command.run(
        ["display-message", "-p", "-t", pane, "|".join(f"#{{{field}}}" for field in fields)]
    )
    values = result.stdout.strip().split("|")
    if result.returncode or len(values) != len(fields):
        return None

    (
        actual,
        marked,
        managed,
        enabled,
        position,
        session,
        window,
        zoomed,
        width,
        height,
        pane_width,
        pane_height,
        saved_width,
        saved_height,
        epoch,
        panes,
    ) = values
    if (
        actual != pane
        or marked != "1"
        or managed != pane
        or enabled != "on"
        or position not in follow.MIN_MAIN
        or session.startswith("_lma_")
        or zoomed != "0"
    ):
        return None

    clients = command.run(
        ["list-clients", "-F", "#{client_name}|#{window_id}|#{client_width}|#{client_height}"]
    )
    visible = sorted(
        line
        for line in clients.stdout.splitlines()
        if len(line.split("|")) == 4 and line.split("|")[1] == window
    )
    if clients.returncode or not visible:
        return None

    try:
        left = position == "left"
        available = min(
            int(width if left else height),
            *(
                int(line.split("|")[2 if left else 3] or (width if left else height))
                for line in visible
            ),
        )
        saved = int(saved_width if left else saved_height)
        size = int(pane_width if left else pane_height)
    except ValueError:
        return None

    expected = max(1, min(saved, available - follow.MIN_MAIN[position]))
    return _Sample(
        (pane, window, position, width, height, saved_width, saved_height, epoch, panes, *visible),
        position,
        size,
        expected,
    )


class Observer:
    """Owns one pending candidate; transitions establish a fresh baseline."""

    def __init__(self) -> None:
        self._previous: _Sample | None = None
        self._candidate: _Sample | None = None
        self._since = 0.0

    def poll(self, now: float | None = None) -> None:
        pane = os.environ.get("TMUX_PANE", "")
        sample = _sample(pane) if pane else None
        now = time.monotonic() if now is None else now
        previous = self._previous
        self._previous = sample
        if sample is None or previous is None or sample.context != previous.context:
            self._candidate = None
            return

        if sample.size == sample.expected:
            self._candidate = None
            return

        if sample.size != previous.size:
            self._candidate = sample
            self._since = now
            return

        if self._candidate != sample or now - self._since < _SETTLE_SECONDS:
            return

        # Capture the axis and size here. Persistence never re-measures a pane
        # that a follow hook may already have moved to another window.
        if _sample(pane) == sample:
            scratch.save_size(sample.position, str(sample.size))
        self._candidate = None
