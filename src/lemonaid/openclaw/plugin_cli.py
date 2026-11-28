"""`lemonaid openclaw plugin`: install, remove or check lemonaid's plugin in OpenClaw's gateway."""

import argparse
import subprocess

from . import plugin_install, sessions


def _install(args: argparse.Namespace) -> None:
    try:
        plugin_install.install(sessions.cli())
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"stopped: {error}; run this again once it is fixed") from error

    print(plugin_install.status())


def _uninstall(args: argparse.Namespace) -> None:
    plugin_install.uninstall(sessions.cli())
    print(plugin_install.status())


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "plugin",
        help="lemonaid's plugin in OpenClaw's gateway, which reports turns and tool calls",
    )
    actions = parser.add_subparsers(dest="action")
    actions.add_parser(
        "install",
        help="install or update it; changes OpenClaw's config and reloads the plugin",
    ).set_defaults(func=_install)
    actions.add_parser("uninstall", help="remove it from OpenClaw").set_defaults(func=_uninstall)
    actions.add_parser("status", help="whether it is installed and current").set_defaults(
        func=lambda a: print(plugin_install.status())
    )
    parser.set_defaults(func=lambda a: parser.print_help())
