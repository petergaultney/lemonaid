"""WezTerm as a front end: a lemon is a pane in a workspace of a GUI instance."""

import json
import subprocess
from collections import abc

from .. import wezterm
from ..config import Config
from . import interface


def _pane_for_tty(tty: str) -> tuple[str | None, int | None]:
    """The workspace and pane ID of the pane on *tty*."""
    try:
        result = subprocess.run(
            ["wezterm", "cli", "list", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        panes = json.loads(result.stdout)

        for pane in panes:
            if pane.get("tty_name") == tty:
                return pane.get("workspace"), pane.get("pane_id")

    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        pass

    return None, None


def show(
    metadata: interface.Metadata | None,
    config: Config,
    on_resume: abc.Callable[[str], None] | None = None,
) -> bool:
    """Switch to its workspace and pane."""
    if metadata is None:
        return False

    workspace = None
    pane_id = None

    if config.wezterm.resolve_pane == "metadata":
        # Use workspace/pane_id directly from metadata
        workspace = metadata.get("workspace")
        pane_id = metadata.get("pane_id")
    elif config.wezterm.resolve_pane == "tty":
        # Resolve from TTY by querying wezterm cli list
        tty = metadata.get("tty")
        if tty:
            workspace, pane_id = _pane_for_tty(tty)

    if workspace is None or pane_id is None:
        # Fallback to metadata if TTY resolution failed
        workspace = metadata.get("workspace")
        pane_id = metadata.get("pane_id")

    if workspace is None or pane_id is None:
        return False

    return wezterm.navigation.switch_to_pane(workspace, pane_id)


def exists(tty: str, socket: str | None = None, not_after: float | None = None) -> bool | None:
    workspace, pane_id = _pane_for_tty(tty)
    return workspace is not None and pane_id is not None


def terminal() -> interface.Terminal:
    return interface.Terminal(
        name="wezterm", here=lambda: bool(wezterm.spawn.own_pane()[0]), show=show, exists=exists
    )
