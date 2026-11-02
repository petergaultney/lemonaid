"""`lemonaid grove move|resize|reshape|clear-open`: rearrange the grove from the command line."""

__lazy_modules__ = ["lemonaid.grove.source"]

import argparse
import json
import sys
from collections import abc
from typing import Any

from ..config import load_config
from .layout import edit, state
from .source import live


def _fail(args: argparse.Namespace, error: str) -> None:
    if args.json:
        print(json.dumps({"error": error}))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(1)


def _open_index(args: argparse.Namespace) -> int | None:
    """N for a BLOCK argument `open:N`, else None."""
    if not args.block.startswith(edit.OPEN):
        return None
    index = args.block.removeprefix(edit.OPEN)
    if not index.isdigit():
        _fail(args, f"{args.block!r} isn't open ground; use open:0, open:1, ...")
    return int(index)


def _group(args: argparse.Namespace) -> str:
    """The group a BLOCK argument names: a digit as the grove numbers it, else a group name."""
    if not args.block.isdigit():
        return args.block

    grove = live.fresh(load_config(), None)
    found = next((block.name for block in grove.blocks if block.digit == args.block), None)
    if found is None:
        _fail(args, f"No block {args.block}; blocks are {', '.join(b.digit for b in grove.blocks)}")
    return found or ""


def _apply(
    args: argparse.Namespace, change: abc.Callable[[dict[str, Any], str], dict[str, Any]]
) -> None:
    index = _open_index(args)
    if index is not None:
        live.fresh(load_config(), None)  # lays out, so ground a group just left is marked open

    group = "" if index is not None else _group(args)
    named: list[str] = []

    def apply(saved: dict[str, Any]) -> dict[str, Any]:
        key = group if index is None else edit.open_key(saved, index)
        named.append(key)
        return change(saved, key)

    try:
        changed = state.update(apply)
    except edit.EditError as error:
        _fail(args, str(error))
        raise
    plot = changed["plots"][named[-1]]
    group = args.block if index is not None else group
    if args.json:
        print(json.dumps({"group": group, "plot": plot, "error": None}))
    else:
        print(f"{group or 'no group'}: {plot['w']}x{plot['h']} at {plot['x']},{plot['y']}")


def _cmd_move(args: argparse.Namespace) -> None:
    _apply(args, lambda saved, group: edit.move(saved, group, args.x, args.y))


def _cmd_resize(args: argparse.Namespace) -> None:
    _apply(args, lambda saved, group: edit.resize(saved, group, args.w, args.h))


def _cmd_reshape(args: argparse.Namespace) -> None:
    _apply(args, lambda saved, group: edit.reshape(saved, group, args.roundness))


def _cmd_clear_open(args: argparse.Namespace) -> None:
    cleared: list[str] = []
    index = None
    if args.open:
        args.block = args.open
        index = _open_index(args)
        if index is None:
            _fail(args, f"{args.open!r} isn't open ground; use open:0, open:1, ...")
        live.fresh(load_config(), None)

    def clear(saved: dict[str, Any]) -> dict[str, Any]:
        changed, gone = edit.clear_open(saved, index)
        cleared.extend(gone)
        return changed

    try:
        state.update(clear)
    except edit.EditError as error:
        _fail(args, str(error))
    if args.json:
        print(json.dumps({"cleared": cleared, "error": None}))
    else:
        print(f"Cleared open ground left by {', '.join(cleared)}" if cleared else "No open ground")


def add_parsers(grove_subparsers: argparse._SubParsersAction) -> None:
    def block_parser(name: str, help_text: str) -> argparse.ArgumentParser:
        parser = grove_subparsers.add_parser(name, help=help_text)
        parser.add_argument(
            "block", help="A block's digit, a group's name, or open:N for open ground"
        )
        parser.add_argument("--json", action="store_true", help="Print the result as JSON")
        return parser

    move = block_parser("move", "Move a block's plot so its top-left corner is at X, Y")
    move.add_argument("x", type=int)
    move.add_argument("y", type=int)
    move.set_defaults(func=_cmd_move)

    resize = block_parser("resize", "Give a block's plot a new width and height")
    resize.add_argument("w", type=int)
    resize.add_argument("h", type=int)
    resize.set_defaults(func=_cmd_resize)

    reshape = block_parser("reshape", "Make a block rounder (2) or squarer (up to 12)")
    reshape.add_argument("roundness", type=float)
    reshape.set_defaults(func=_cmd_reshape)

    clear = grove_subparsers.add_parser(
        "clear-open", help="Forget open ground left by groups that ended, or just open:N"
    )
    clear.add_argument("open", nargs="?", default="", help="One open ground, as open:N")
    clear.add_argument("--json", action="store_true", help="Print the result as JSON")
    clear.set_defaults(func=_cmd_clear_open)
