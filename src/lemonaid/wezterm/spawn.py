"""Starting a shell in a new WezTerm tab and typing a line into it."""

import os
from collections import abc

from . import client


def _shell() -> str:
    return os.environ.get("SHELL") or "/bin/sh"


def own_pane() -> tuple[str, str | None]:
    """The calling pane's ID and its instance's socket; ("", None) outside WezTerm."""
    pane = os.environ.get("WEZTERM_PANE", "")
    return (pane, os.environ.get(client.SOCKET_ENV) or None) if pane.isdigit() else ("", None)


def spawn_args(where: abc.Sequence[str], cwd: str, environment: abc.Mapping[str, str]) -> list[str]:
    """`cli spawn`'s arguments; it has no flag for the shell's environment, so `env` sets it."""
    shell = (
        ["--", "env", *(f"{name}={value}" for name, value in environment.items()), _shell()]
        if environment
        else []
    )
    return ["spawn", *where, "--cwd", cwd, *shell]


def tab_beside(
    pane: str, cwd: str, environment: abc.Mapping[str, str], socket: str | None
) -> tuple[str, str]:
    """The ID of a new pane in a new tab of *pane*'s window, and "" - or "" and why not."""
    opened = client.run(spawn_args(["--pane-id", pane], cwd, environment), socket)
    new = opened.stdout.strip()
    if opened.returncode != 0 or not new.isdigit():
        return "", f"Could not open a WezTerm tab beside pane {pane}: {opened.stderr.strip()}"

    return new, ""


def workspace_of(pane: str, socket: str | None) -> str:
    """The workspace *pane* is in, or "" if WezTerm doesn't list it."""
    found = (p for p in client.panes(socket) or [] if str(p.get("pane_id")) == pane)
    return next((p.get("workspace", "") for p in found), "")


def type_line(pane: str, line: str, socket: str | None) -> str:
    """Type *line* and Enter into *pane*'s shell. Returns an error, or ""."""
    typed = client.run(["send-text", "--no-paste", "--pane-id", pane, line + "\r"], socket)
    return "" if typed.returncode == 0 else f"Could not type into WezTerm pane {pane}"
