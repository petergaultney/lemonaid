"""A `tmux` for the suite that refuses any command bound for the developer's own server.

conftest puts it first on PATH, so it stands in for tmux in every process a test starts,
whatever the test does with TMUX, TMUX_TMPDIR or the environment it passes on. A refused
command exits 1 and is recorded, so the test fails even when the code under test shrugs
off a failed tmux command. A test that runs tmux by its full path gets past it.
"""

import os
import shlex
import typing as ty
from collections import abc
from pathlib import Path

_BODY = Path(__file__).with_name("tmux_guard.sh")


class Guard(ty.NamedTuple):
    bin: Path  # holds only the guard's `tmux`
    refusals: Path


def guarded(attached: str, tmpdir: str) -> list[str]:
    """The servers a test must not reach: the one in *attached*, a TMUX value, and tmux's
    default under *tmpdir*, a TMUX_TMPDIR value, and under /tmp, where tmux falls back."""
    defaults = (str(Path(d) / f"tmux-{os.getuid()}" / "default") for d in (tmpdir, "/tmp") if d)
    servers = (attached.split(",", 1)[0], *defaults)
    return list(dict.fromkeys(os.path.realpath(s) for s in servers if s))


def install(directory: Path, real: str, servers: abc.Iterable[str]) -> Guard | None:
    """Write a guard for *servers* into *directory*, in front of the tmux at *real*; None
    when there is no tmux to guard."""
    if not real:
        return None

    guard = Guard(directory / "bin", directory / "refusals")
    values = {
        "real": real,
        "uid": str(os.getuid()),
        "guarded": ":".join(servers),
        "refusals": str(guard.refusals),
    }
    guard.bin.mkdir(parents=True)
    script = guard.bin / "tmux"
    script.write_text(
        "\n".join(
            ["#!/bin/sh", *(f"{k}={shlex.quote(v)}" for k, v in values.items()), _BODY.read_text()]
        )
    )
    script.chmod(0o755)
    return guard


def take(guard: Guard) -> str:
    """The commands refused since the last call, which it forgets."""
    try:
        refused = guard.refusals.read_text()
    except FileNotFoundError:
        return ""

    guard.refusals.unlink()
    return refused
