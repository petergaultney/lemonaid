"""Where a lemon runs, read the same way whichever front end (terminal) recorded it.

Only a front end's own module interprets `instance`, `slot` and `pane`; everything else
compares them for equality. A tmux session run inside cmux or WezTerm is tmux's.
"""

import dataclasses
import typing as ty
from collections import abc


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
