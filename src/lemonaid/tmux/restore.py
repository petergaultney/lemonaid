"""Rebuilding a tmux layout from the inbox after the server is lost.

When tmux dies, the sessions are gone but the inbox is not: it still holds every
active lemon, its cwd, and - since notifications record it - the session and
window it was sitting in. That is enough to put the layout back.

Planning is separated from doing because the plan is the part worth reading
before anything spawns: restoring a day's work means starting many processes at
once, and `--dry-run` is what makes that inspectable first.
"""

import shlex
import subprocess
import typing as ty
from collections import abc

from ..config import Config
from ..inbox.db import Notification
from ..log import get_logger
from ..resume import build_resume_command
from . import session as tmux_session

_log = get_logger("tmux.restore")

_SPAWN_TIMEOUT_SECONDS = 10


class Window(ty.NamedTuple):
    index: int
    cwd: str
    argv: list[str]
    name: str  # the inbox's name for the lemon, for display only

    @property
    def command(self) -> str:
        return " ".join(shlex.quote(a) for a in self.argv)


class SessionPlan(ty.NamedTuple):
    name: str
    windows: list[Window]  # ascending by index, never empty


def _window(notification: Notification, config: Config) -> Window | None:
    """What to put back for one notification, or None if it can't be restored."""
    index = notification.metadata.get("tmux_window")
    if index is None:
        return None

    resumable = build_resume_command(config, notification.channel, notification.metadata)
    if resumable is None:
        return None

    cwd, argv = resumable

    try:
        return Window(int(index), cwd, argv, notification.name or notification.channel)
    except ValueError:
        _log.warning("ignoring unparseable window index %r for %s", index, notification.channel)
        return None


def plan_restore(notifications: abc.Iterable[Notification], config: Config) -> list[SessionPlan]:
    """What it would take to rebuild the tmux layout these notifications describe.

    Pure: it starts nothing and inspects no live tmux, so the result can be shown
    before anything happens.

    A notification with no recorded `tmux_session` is left out - there is nowhere
    to put it, and guessing a session for it would invent a layout rather than
    restore one. Sessions observed before lemonaid began recording the location
    are all of this kind.
    """
    grouped: dict[str, list[Window]] = {}
    for notification in notifications:
        name = notification.metadata.get("tmux_session")
        if not name:
            continue

        window = _window(notification, config)
        if window is not None:
            grouped.setdefault(name, []).append(window)

    return [
        SessionPlan(name, sorted(windows)) for name, windows in sorted(grouped.items()) if windows
    ]


def describe(plans: abc.Sequence[SessionPlan]) -> list[str]:
    """The plan as lines, for a person deciding whether to run it."""
    if not plans:
        return ["Nothing to restore: no active session records where it was running."]

    return [
        line
        for plan in plans
        for line in [
            f"{plan.name}",
            *(f"  {w.index}: {w.name} ({w.cwd})" for w in plan.windows),
        ]
    ]


def as_json(plans: abc.Sequence[SessionPlan]) -> list[dict]:
    """The plan as plain data, for a caller driving this rather than reading it."""
    return [
        {
            "session": plan.name,
            "windows": [
                {"index": w.index, "cwd": w.cwd, "name": w.name, "argv": w.argv}
                for w in plan.windows
            ],
        }
        for plan in plans
    ]


def _run(*argv: str) -> bool:
    try:
        subprocess.run(argv, check=True, capture_output=True, timeout=_SPAWN_TIMEOUT_SECONDS)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("%s failed: %s", " ".join(argv), e)
        return False


def _existing_sessions() -> set[str]:
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=_SPAWN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not list sessions: %s", e)
        return set()

    # A missing server exits non-zero with "no server running", which is the
    # normal case here rather than a failure - nothing exists to collide with.
    return set(result.stdout.split()) if result.returncode == 0 else set()


def _client_size() -> tuple[str, str]:
    """The size to build a detached session at.

    A detached session with no size is 80x24, and stays that way until a client
    shows it. The scratch pane splits its saved width off whatever the window
    reports, so in an 80-column window a 48-column sidebar leaves 32 for your
    work - and the swap that would fix it is capped against the client, which
    is wide enough that nothing looks wrong. The pane you see is the
    placeholder: a bare `sleep`, which renders as an empty pane.
    """
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#{client_width} #{client_height}"],
        capture_output=True,
        text=True,
        timeout=_SPAWN_TIMEOUT_SECONDS,
    )
    parts = result.stdout.split()

    return (parts[0], parts[1]) if len(parts) == 2 and parts[0].isdigit() else ("200", "50")


def _restore_session(plan: SessionPlan) -> str | None:
    """Create *plan*'s session and its windows. Returns an error message or None.

    Windows are placed at their recorded indices, so a window the inbox knows
    nothing about - an editor, a shell - leaves a gap that comes back empty
    rather than shifting every later window down.
    """
    first = plan.windows[0]
    width, height = _client_size()
    if not _run(
        "tmux",
        "new-session",
        "-d",
        "-s",
        plan.name,
        "-c",
        first.cwd,
        "-n",
        str(first.index),
        "-x",
        width,
        "-y",
        height,
    ):
        return f"Could not create session {plan.name!r}"

    # tmux numbers the first window itself, so move it to the recorded index
    # before anything else is added and the number is taken.
    _run("tmux", "move-window", "-s", f"{plan.name}:^", "-t", f"{plan.name}:{first.index}")
    _run("tmux", "send-keys", "-t", f"{plan.name}:{first.index}", first.command, "Enter")

    for window in plan.windows[1:]:
        if not _run(
            "tmux", "new-window", "-d", "-t", f"{plan.name}:{window.index}", "-c", window.cwd
        ):
            _log.warning("skipping window %d of %s", window.index, plan.name)
            continue

        _run("tmux", "send-keys", "-t", f"{plan.name}:{window.index}", window.command, "Enter")

    return None


def restore(plans: abc.Sequence[SessionPlan]) -> tuple[list[str], list[str]]:
    """Create every session in *plans* that isn't already running.

    Returns (restored, skipped) session names. An existing session is left
    untouched rather than added to: after a crash you have usually rebuilt some
    of them by hand already, and those are the ones worth not disturbing.
    """
    live = _existing_sessions()
    restored: list[str] = []
    skipped: list[str] = []

    for plan in plans:
        if tmux_session.sanitize_name(plan.name) in live or plan.name in live:
            skipped.append(plan.name)
            continue

        if error := _restore_session(plan):
            _log.warning("%s", error)
            continue

        restored.append(plan.name)

    return restored, skipped
