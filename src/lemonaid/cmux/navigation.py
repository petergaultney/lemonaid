"""Find and focus the cmux surface a session runs in, or open one for it.

One rule says where a session is, and both the switch and the watcher use it:

1. The surface lemonaid recorded (`cmux_surface`), while it still has the
   recorded tty. Either alone can be reused: a tty name by another surface, and
   a surface by another program after the session's agent exits.
2. A surface cmux has bound to the session (`resume_binding`) and where its
   agent is running. cmux resumes its agents there after a restart, on new
   ttys, so this is where a session that has moved is found.
3. For a row recorded without a surface, the surface on its tty.
"""

import json
import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from ..log import get_logger

_log = get_logger("cmux")

# The watcher asks every tick, so a hung cmux must not stall it for long.
_QUERY_TIMEOUT_SECONDS = 0.5
_ACTION_TIMEOUT_SECONDS = 5

# `list-panels` answers for one workspace at a time: about 0.7 s for 31 of them.
# The watcher reuses a sweep for this long; a switch always makes a fresh one.
_SWEEP_SECONDS = 10.0

# Several live surfaces run the session, so none of them is the one.
AMBIGUOUS = "__ambiguous__"
# Whether the agent runs on some surface could not be told.
UNKNOWN = "__unknown__"

HarnessCheck = Callable[[dict[str, Any], str], bool | None]
"""Whether the agent of the session in *metadata* runs on *tty*, or None if unknown."""


class CmuxUnavailable(Exception):
    """cmux did not answer, so whether a surface exists is unknown."""


@dataclass(frozen=True)
class Surface:
    window: str
    workspace: str
    surface: str


_answering = True
_swept: tuple[float, dict[str, list[tuple[str, Surface]]]] | None = None


def _cmux(*args: str, timeout: float = _ACTION_TIMEOUT_SECONDS) -> str:
    result = subprocess.run(
        ["cmux", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )
    return result.stdout


def _json(*args: str) -> dict:
    """Ask cmux, logging only when it stops or starts answering.

    An `lma` that cannot reach cmux would otherwise log on every watcher tick.
    """
    global _answering

    try:
        answer = json.loads(
            _cmux("--json", "--id-format", "uuids", *args, timeout=_QUERY_TIMEOUT_SECONDS)
        )
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as e:
        if _answering:
            _log.warning("cmux stopped answering (%s): %s", " ".join(args), e)
        _answering = False
        raise CmuxUnavailable from e

    if not _answering:
        _log.info("cmux is answering again")
    _answering = True

    return answer


def _terminals() -> dict[str, tuple[str, Surface]]:
    """Every terminal surface in every window, by id, with its tty as lemonaid records it.

    cmux reports a tty without its `/dev/` prefix. Raises CmuxUnavailable when
    cmux cannot be asked, which is not the same answer as "no surfaces".
    """
    tree = _json("tree", "--all")
    return {
        surface["id"]: (
            f"/dev/{surface['tty']}",
            Surface(window["id"], workspace["id"], surface["id"]),
        )
        for window in tree.get("windows", [])
        for workspace in window.get("workspaces", [])
        for pane in workspace.get("panes", [])
        for surface in pane.get("surfaces", [])
        if surface.get("tty")
    }


def _sweep(terminals: dict[str, tuple[str, Surface]]) -> dict[str, list[tuple[str, Surface]]]:
    """The terminal surfaces bound to each agent session, with their ttys.

    A binding outlives its agent, and one session can be bound to two surfaces,
    which is why rule 2 checks what runs on each.
    """
    global _swept

    workspaces = sorted({(surface.window, surface.workspace) for _, surface in terminals.values()})
    bound: dict[str, list[tuple[str, Surface]]] = {}
    for window, workspace in workspaces:
        panels = _json("list-panels", "--workspace", workspace, "--window", window)
        for panel in panels.get("surfaces", []):
            session_id = (panel.get("resume_binding") or {}).get("checkpoint_id")
            if session_id and panel.get("id") in terminals:
                bound.setdefault(session_id, []).append(terminals[panel["id"]])

    _swept = (time.monotonic(), bound)
    return bound


class _View:
    """cmux as one caller sees it: the tree now, and bindings only if a row needs them."""

    def __init__(self, reuse_sweep: bool) -> None:
        self.terminals = _terminals()
        self._reuse_sweep = reuse_sweep
        self._bound: dict[str, list[tuple[str, Surface]]] | None = None

    def bound(self, session_id: str) -> list[tuple[str, Surface]]:
        if self._bound is None:
            recent = _swept is not None and time.monotonic() - _swept[0] < _SWEEP_SECONDS
            self._bound = _swept[1] if self._reuse_sweep and recent else _sweep(self.terminals)

        return self._bound.get(session_id, [])


def _candidates(
    metadata: dict[str, Any], view: _View, runs_harness: HarnessCheck
) -> list[tuple[str, Surface]] | None:
    """The (tty, surface) pairs the module's rule finds the session in; None if unknown.

    More than one means the session runs on several surfaces.
    """
    tty = metadata.get("tty")
    recorded = metadata.get("cmux_surface")
    if recorded in view.terminals:
        found = view.terminals[recorded]
        if tty is None or found[0] == tty:
            return [found]

    session_id = metadata.get("session_id")
    if session_id:
        running = []
        for found in view.bound(session_id):
            runs = runs_harness(metadata, found[0])
            if runs is None:
                return None
            if runs:
                running.append(found)

        if running:
            return running

    if recorded is None and tty:
        return [found for found in view.terminals.values() if found[0] == tty]

    return []


def locate(metadata: dict[str, Any], runs_harness: HarnessCheck) -> Surface | str | None:
    """The surface the session is in now, AMBIGUOUS, UNKNOWN, or None if it is in none.

    Raises CmuxUnavailable when cmux does not answer.
    """
    found = _candidates(metadata, _View(reuse_sweep=False), runs_harness)
    if found is None:
        return UNKNOWN
    if len(found) > 1:
        return AMBIGUOUS

    return found[0][1] if found else None


def where(
    sessions: list[dict[str, Any]], runs_harness: HarnessCheck, reuse_sweep: bool = True
) -> dict[str, str | Literal[False] | None]:
    """For each session's `channel`: the tty it runs on now, False if gone, None if unknown.

    One `cmux tree` for all of them, and a sweep of bindings only when one is
    not where it was recorded. A session on several surfaces is answered with
    one of their ttys: it is running, which is all the watcher asks.
    """
    try:
        view = _View(reuse_sweep=reuse_sweep)
    except CmuxUnavailable:
        return {session["channel"]: None for session in sessions}

    answers: dict[str, str | Literal[False] | None] = {}
    for session in sessions:
        try:
            found = _candidates(session, view, runs_harness)
        except CmuxUnavailable:
            found = None

        if found is None:
            answers[session["channel"]] = None
        else:
            answers[session["channel"]] = found[0][0] if found else False

    return answers


def switch_to_surface(target: Surface) -> bool:
    """Focus *target*, which brings its workspace forward too."""
    try:
        _cmux(
            "focus-panel",
            "--panel",
            target.surface,
            "--workspace",
            target.workspace,
            "--window",
            target.window,
        )
    except (subprocess.SubprocessError, OSError) as e:
        _log.warning("could not switch to cmux surface %s: %s", target.surface, e)
        return False

    return True


def open_workspace(cwd: str, argv: list[str], name: str, focus: bool = True) -> bool:
    """Run *argv* in a new workspace rooted at *cwd*, focused unless *focus* is False.

    cmux types `--command` into the workspace's shell, so it is quoted for one.
    """
    try:
        _cmux(
            "new-workspace",
            "--name",
            name,
            "--cwd",
            cwd,
            "--command",
            shlex.join(argv),
            "--focus",
            "true" if focus else "false",
        )
    except (subprocess.SubprocessError, OSError) as e:
        _log.warning("could not open a cmux workspace in %s: %s", cwd, e)
        return False

    return True
