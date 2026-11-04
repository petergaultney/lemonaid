"""Where `lemon start` puts a lemon: a named tmux window, or beside the caller in its terminal."""

import argparse
import os
import sys
from pathlib import Path

from .. import cmux, wezterm
from ..config import Config
from ..watch import children_waiter
from . import handoff, plan, window


def _handed_off(
    planned: plan.Plan, session: str = "", index: str = "", window_id: str = ""
) -> None:
    if warning := handoff.complete(planned.given, session, index, window_id, planned.token):
        print(f"Warning: {warning}", file=sys.stderr)
    if planned.given.link:
        print(children_waiter.reminder(), file=sys.stderr)


def _typed_in_tmux(
    args: argparse.Namespace,
    planned: plan.Plan,
    directory: Path,
    where: tuple[str, str, window.Pane],
) -> tuple[dict, str]:
    session, index, pane = where
    result = plan.result(
        planned,
        directory,
        front_end="tmux",
        where=f"tmux window {session}:{index}",
        session=session,
        window=index,
        window_id=pane.window_id,
    )
    _handed_off(planned, session, index, pane.window_id)
    if error := window.run(pane, planned.typed):
        return result, error

    if not args.no_check and (dialog := window.startup_dialog(pane.pane_id)):
        return result, f"The lemon in {session}:{index} is waiting at {dialog}"

    return result, ""


def in_window(
    args: argparse.Namespace, config: Config, session: str, index: str
) -> tuple[dict, str]:
    """Window *index* of *session*, in the session's directory."""
    directory = window.session_dir(session)
    if directory is None:
        return {}, f"No tmux session {session!r}"

    planned, error = plan.plan(args, config, directory)
    if planned is None:
        return {}, error

    pane, error = window.open_window(session, index, directory, planned.environment)
    if pane is None:
        return {}, error

    return _typed_in_tmux(args, planned, directory, (session, index, pane))


def in_new_window(args: argparse.Namespace, config: Config, session: str) -> tuple[dict, str]:
    """A new window of the caller's own tmux session, in the current directory."""
    directory = Path.cwd()
    planned, error = plan.plan(args, config, directory)
    if planned is None:
        return {}, error

    pane, index, error = window.new_window(session, directory, planned.environment)
    if pane is None:
        return {}, error

    return _typed_in_tmux(args, planned, directory, (session, index, pane))


def in_new_tab(
    args: argparse.Namespace, config: Config, pane: str, socket: str | None
) -> tuple[dict, str]:
    """A new WezTerm tab beside the caller's pane, in the current directory."""
    directory = Path.cwd()
    planned, error = plan.plan(args, config, directory)
    if planned is None:
        return {}, error

    new_pane, error = wezterm.spawn.tab_beside(pane, str(directory), planned.environment, socket)
    if not new_pane:
        return {}, error

    _handed_off(planned)
    workspace = wezterm.spawn.workspace_of(new_pane, socket)
    result = plan.result(
        planned,
        directory,
        front_end="wezterm",
        where=f"WezTerm pane {new_pane}" + (f" in workspace {workspace}" if workspace else ""),
        wezterm_pane=new_pane,
        wezterm_workspace=workspace,
    )
    return result, wezterm.spawn.type_line(new_pane, planned.typed, socket)


def in_new_cmux_workspace(args: argparse.Namespace, config: Config) -> tuple[dict, str]:
    """A new, unfocused cmux workspace in the current directory.

    cmux types the command into the workspace's shell and has no flag for its
    environment, so `env` sets it around the caller's own shell.
    """
    directory = Path.cwd()
    planned, error = plan.plan(args, config, directory)
    if planned is None:
        return {}, error

    name = planned.given.name or directory.name
    shell = [
        "env",
        *(f"{variable}={value}" for variable, value in planned.environment.items()),
        os.environ.get("SHELL") or "/bin/sh",
        "-c",
        planned.typed,
    ]
    if not cmux.navigation.open_workspace(str(directory), shell, name, focus=False):
        return {}, "cmux could not open a workspace for it"

    _handed_off(planned)
    return plan.result(
        planned, directory, front_end="cmux", where=f"cmux workspace {name}", cmux_workspace=name
    ), ""
