"""The tmux server restore opens windows on: the one the caller runs under, else tmux's
default. A lemon recorded on any other server is not brought back onto this one."""

import os
import typing as ty
from collections import abc
from pathlib import Path

from . import navigation


def socket() -> str:
    return navigation.current_socket() or str(
        Path(os.environ.get("TMUX_TMPDIR") or "/tmp") / f"tmux-{os.getuid()}" / "default"
    )


def elsewhere(metadata: abc.Mapping[str, ty.Any]) -> str:
    """The other server a row recorded, or "" when it is this one or it recorded none."""
    recorded = str(metadata.get("tmux_socket") or "")
    return recorded if recorded and os.path.realpath(recorded) != os.path.realpath(socket()) else ""
