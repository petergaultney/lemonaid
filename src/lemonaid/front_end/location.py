"""Where a lemon runs, read the same way whichever front end (terminal) recorded it.

Only a front end's own module interprets `instance`, `slot` and `pane`; everything else
compares them for equality. A tmux session run inside cmux or WezTerm is tmux's.
"""

import dataclasses
import typing as ty
from collections import abc

from .. import wezterm
from ..lemon_watchers import common


@dataclasses.dataclass(frozen=True)
class Location:
    front_end: str  # "tmux", "wezterm", "cmux", "plain" (a tty only), or "" (nothing recorded)
    instance: str = ""  # the tmux server's or WezTerm GUI's socket
    workspace: str = ""  # tmux session or WezTerm workspace: what "near me" means
    slot: str = ""  # tmux window index; WezTerm and cmux record none
    pane: str = ""  # tmux pane ID, WezTerm pane ID or cmux surface
    tty: str = ""


def _text(metadata: abc.Mapping[str, ty.Any], key: str) -> str:
    value = metadata.get(key)
    return "" if value is None else str(value)


def _tmux_pane(metadata: abc.Mapping[str, ty.Any]) -> str:
    identity = metadata.get("tmux_pane_identity")
    return str(identity[0]) if isinstance(identity, list) and identity else ""


def _tmux(metadata: abc.Mapping[str, ty.Any]) -> Location:
    return Location(
        "tmux",
        _text(metadata, "tmux_socket"),
        _text(metadata, "tmux_session"),
        _text(metadata, "tmux_window"),
        _tmux_pane(metadata),
        _text(metadata, "tty"),
    )


def _wezterm(metadata: abc.Mapping[str, ty.Any]) -> Location:
    return Location(
        "wezterm",
        _text(metadata, "wezterm_socket"),
        _text(metadata, "wezterm_workspace"),
        "",
        _text(metadata, "wezterm_pane"),
        _text(metadata, "tty"),
    )


def _cmux(metadata: abc.Mapping[str, ty.Any]) -> Location:
    return Location("cmux", pane=_text(metadata, "cmux_surface"), tty=_text(metadata, "tty"))


_FIELDS = {"tmux": _tmux, "wezterm": _wezterm, "cmux": _cmux}


def _inferred(metadata: abc.Mapping[str, ty.Any]) -> str:
    if metadata.get("tmux_session"):
        return "tmux"

    if metadata.get("wezterm_pane") is not None and metadata.get("wezterm_workspace"):
        return "wezterm"

    if metadata.get("cmux_surface"):
        return "cmux"

    return "plain" if metadata.get("tty") else ""


def of(metadata: abc.Mapping[str, ty.Any], switch_source: str = "") -> Location:
    """The location an inbox row's *metadata* records.

    *switch_source*, the terminal its hook last ran in, picks which keys to read: a
    conversation that moved terminals keeps the keys of the one it left.
    """
    front_end = switch_source or _inferred(metadata)
    fields = _FIELDS.get(front_end)
    return fields(metadata) if fields else Location(front_end, tty=_text(metadata, "tty"))


def here() -> Location:
    """Where the calling process runs, read from its environment the way a hook records a
    lemon's location. Outside every front end it knows, the front end is "plain"."""
    match common.detect_terminal_switch_source():
        case "tmux":
            return Location(
                "tmux", common.get_tmux_socket() or "", common.get_tmux_session_name() or ""
            )
        case "wezterm":
            return _wezterm(wezterm.location.metadata())
        case "cmux":
            return Location("cmux", pane=common.get_cmux_surface() or "")
    return Location("plain")


def near(one: Location, other: Location) -> bool:
    """Whether two locations share a workspace (a tmux session, a WezTerm workspace) on the
    same instance of the same front end. A front end that records no workspace (cmux) is
    near nothing."""
    return bool(one.workspace) and (one.front_end, one.instance, one.workspace) == (
        other.front_end,
        other.instance,
        other.workspace,
    )
