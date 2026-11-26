"""`lemonaid grove serve`: the grove in a browser, for a machine reached over a network."""

__lazy_modules__ = ["lemonaid.grove.web.server"]

import argparse
import subprocess
import sys

from ...config import load_config
from .server import serve

DEFAULT_PORT = 8770


def _tailnet_address() -> str:
    """This machine's Tailscale IPv4 address, or "" when Tailscale can't say."""
    try:
        cp = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    return cp.stdout.split()[0] if cp.returncode == 0 and cp.stdout.split() else ""


def _cmd_serve(args: argparse.Namespace) -> None:
    host = args.host or _tailnet_address()
    if not host:
        sys.exit("No Tailscale address found; pass --host to choose where to listen")

    serve(load_config(), host, args.port, args.name)


def add_parsers(grove_subparsers: argparse._SubParsersAction) -> None:
    serve = grove_subparsers.add_parser(
        "serve",
        help="Serve the grove to a browser, on this machine's tailnet address",
        description="Serve the grove to a browser. There is no login or encryption: anyone who"
        " can reach the address controls the grove, so listen only on a private network you"
        " control, such as a tailnet, or on 127.0.0.1.",
    )
    serve.add_argument(
        "--host", default="", help="address to listen on (default: `tailscale ip -4`)"
    )
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument(
        "--name", default="lemonaid", help="what a phone calls the grove installed as an app"
    )
    serve.set_defaults(func=_cmd_serve)
