"""Separate launch arguments from harness arguments before argparse reads them."""

import argparse
from collections import abc


def parse_args(parser: argparse.ArgumentParser, argv: abc.Sequence[str]) -> argparse.Namespace:
    launch = tuple(argv[:2]) in (("place", "open"), ("place", "new"), ("lemon", "start")) or tuple(
        argv[:3]
    ) == ("lemon", "presets", "show")
    if launch and "--" in argv:
        boundary = argv.index("--")
        args = parser.parse_args(argv[:boundary])
        args.lemon_args = list(argv[boundary + 1 :])
        return args

    return parser.parse_args(argv)
