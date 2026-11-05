"""Which front end a recorded lemon, or the caller, runs in, with how to start lemons there."""

import argparse

from .. import wezterm
from ..config import Config
from ..launch import where, window
from ..messages import autoresume_cmux, autoresume_tmux, autoresume_wezterm
from . import interface, terminals


def _beside_tmux(args: argparse.Namespace, config: Config) -> tuple[dict, str]:
    return where.in_new_window(args, config, window.own_session())


def _beside_wezterm(args: argparse.Namespace, config: Config) -> tuple[dict, str]:
    return where.in_new_tab(args, config, *wezterm.spawn.own_pane())


def _front_end(terminal: interface.Terminal) -> interface.FrontEnd | None:
    match terminal.name:
        case "tmux":
            return interface.FrontEnd(
                terminal, _beside_tmux, autoresume_tmux.start, autoresume_tmux.prompt
            )
        case "wezterm":
            return interface.FrontEnd(
                terminal, _beside_wezterm, autoresume_wezterm.start, autoresume_wezterm.prompt
            )
        case "cmux":  # cmux can't type into a surface, so an idle lemon there can't be prompted
            return interface.FrontEnd(
                terminal, where.in_new_cmux_workspace, autoresume_cmux.start, None
            )
        case _:
            return None


def named(name: str | None) -> interface.FrontEnd | None:
    """The front end an inbox row's `switch_source` names, or None for one lemonaid doesn't know."""
    terminal = terminals.named(name)
    return _front_end(terminal) if terminal else None


def around_caller() -> interface.FrontEnd | None:
    here = next((each for each in terminals.all_terminals() if each.here()), None)
    return _front_end(here) if here else None
