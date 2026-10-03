"""Rebuilding a tmux layout from the inbox after the server is lost.

When tmux dies, the sessions are gone but the inbox is not: it still holds every
active lemon, its cwd, and - since notifications record it - the session and
window it was sitting in. That is enough to put the layout back.

Planning is separated from doing because the plan is the part worth reading
before anything spawns: restoring a day's work means starting many processes at
once, and `--dry-run` is what makes that inspectable first.
"""

import subprocess
import typing as ty
from collections import abc

from ..config import Config
from ..inbox.db import Notification
from ..launch import window as launch_window
from ..log import get_logger
from ..restore import launch, report
from . import navigation
from . import session as tmux_session

_log = get_logger("tmux.restore")

_SPAWN_TIMEOUT_SECONDS = 10


class Window(ty.NamedTuple):
    index: int
    cwd: str
    line: str
    environment: dict[str, str]
    name: str  # the inbox's name for the lemon, for display only
    channel: str
    rearm: str  # report.PROMPTED, NO_BRIEF, NOTHING_TO_REARM or BY_HAND


class SessionPlan(ty.NamedTuple):
    name: str
    windows: list[Window]  # ascending by index, never empty


def _window(
    notification: Notification, config: Config, prompts: abc.Mapping[str, str]
) -> Window | None:
    """What to put back for one notification, or None if it can't be restored."""
    index = notification.metadata.get("tmux_window")
    if index is None:
        return None

    prompt = prompts.get(notification.channel, "")
    resumed = launch.launch(notification, config, prompt)
    if resumed is None:
        return None

    if resumed.prompted:
        rearm = report.PROMPTED
    elif prompt:
        rearm = report.BY_HAND
    elif notification.channel in prompts:
        rearm = report.NOTHING_TO_REARM
    else:
        rearm = report.NO_BRIEF

    try:
        return Window(
            int(index),
            resumed.cwd,
            resumed.line,
            resumed.environment,
            notification.name or notification.channel,
            notification.channel,
            rearm,
        )
    except ValueError:
        _log.warning("ignoring unparseable window index %r for %s", index, notification.channel)
        return None


def _session_order(notification: Notification) -> navigation.SessionOrder | None:
    """When tmux made this notification's session, if the watcher recorded it."""
    match notification.metadata.get("tmux_session_order"):
        case [int(created), int(server_started), int(session_id)]:
            return created, server_started, session_id
        case _:
            return None


def plan_restore(
    notifications: abc.Iterable[Notification],
    config: Config,
    prompts: abc.Mapping[str, str],
) -> list[SessionPlan]:
    """What it would take to rebuild the tmux layout these notifications describe.

    *prompts* holds the rearm prompt of each channel with a brief, "" for one
    whose brief lists nothing to rearm; a channel missing from it has no brief.

    Pure: it starts nothing and inspects no live tmux, so the result can be shown
    before anything happens.

    A notification with no recorded `tmux_session` is left out - there is nowhere
    to put it, and guessing a session for it would invent a layout rather than
    restore one. Sessions observed before lemonaid began recording the location
    are all of this kind.

    Sessions come back in the order tmux made them, so a listing by creation
    or index looks as it did. A session with no recorded order goes after the
    rest, by name.
    """
    grouped: dict[str, list[Window]] = {}
    orders: dict[str, navigation.SessionOrder] = {}
    for notification in notifications:
        name = notification.metadata.get("tmux_session")
        if not name:
            continue

        window = _window(notification, config, prompts)
        if window is None:
            continue

        grouped.setdefault(name, []).append(window)
        if order := _session_order(notification):
            orders[name] = min(order, orders.get(name, order))

    return [
        SessionPlan(name, sorted(grouped[name], key=lambda w: w.index))
        for name in sorted(grouped, key=lambda n: (n not in orders, orders.get(n, (0, 0, 0)), n))
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
            *(f"  {w.index}: {w.name} ({w.cwd}) [{w.rearm}]" for w in plan.windows),
        ]
    ]


def as_json(plans: abc.Sequence[SessionPlan]) -> list[dict]:
    """The plan as plain data, for a caller driving this rather than reading it."""
    return [
        {
            "session": plan.name,
            "windows": [
                {
                    "index": w.index,
                    "cwd": w.cwd,
                    "name": w.name,
                    "channel": w.channel,
                    "line": w.line,
                    "rearm": w.rearm,
                }
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


def _placed(session: str, window: Window) -> report.Placed:
    return report.Placed(window.channel, window.name, f"{session}:{window.index}", window.rearm)


def _failed(session: str, window: Window, why: str) -> report.Result:
    return report.Result(
        window.channel, window.name, f"{session}:{window.index}", report.NOT_RESTORED, why
    )


class Restored(ty.NamedTuple):
    restored: list[str]  # session names
    skipped: list[str]  # session names already running
    placed: list[report.Placed]  # the lemons started, in the restored sessions
    failed: list[report.Result]  # the lemons that should have been, and why not


def _start(session: str, window: Window) -> report.Placed | report.Result:
    """Type *window*'s line into its pane, which must already exist."""
    if not _run("tmux", "send-keys", "-t", f"{session}:{window.index}", window.line, "Enter"):
        return _failed(session, window, "could not type its line into the window")

    return _placed(session, window)


def _restore_session(plan: SessionPlan) -> list[report.Placed | report.Result]:
    """Create *plan*'s session and its windows: each lemon started, or why it wasn't.

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
        *launch_window.environment_args(first.environment),
    ):
        return [_failed(plan.name, w, "could not create its session") for w in plan.windows]

    # tmux numbers the first window itself, so move it to the recorded index
    # before anything else is added and the number is taken.
    moved = _run("tmux", "move-window", "-s", f"{plan.name}:^", "-t", f"{plan.name}:{first.index}")
    started = [
        _start(plan.name, first)
        if moved
        else _failed(plan.name, first, f"could not move its window to {first.index}")
    ]

    for window in plan.windows[1:]:
        if _run(
            "tmux",
            "new-window",
            "-d",
            "-t",
            f"{plan.name}:{window.index}",
            "-c",
            window.cwd,
            *launch_window.environment_args(window.environment),
        ):
            started.append(_start(plan.name, window))
        else:
            started.append(_failed(plan.name, window, "could not create its window"))

    return started


def restore(plans: abc.Sequence[SessionPlan]) -> Restored:
    """Create every session in *plans* that isn't already running.

    An existing session is left untouched rather than added to: after a crash
    you have usually rebuilt some of them by hand already, and those are the
    ones worth not disturbing.
    """
    live = _existing_sessions()
    done = Restored([], [], [], [])

    for plan in plans:
        if tmux_session.sanitize_name(plan.name) in live or plan.name in live:
            done.skipped.append(plan.name)
            continue

        started = _restore_session(plan)
        done.placed.extend(s for s in started if isinstance(s, report.Placed))
        done.failed.extend(s for s in started if isinstance(s, report.Result))
        if any(isinstance(s, report.Placed) for s in started):
            done.restored.append(plan.name)

    return done
