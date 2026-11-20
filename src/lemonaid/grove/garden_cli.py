"""`lemonaid grove plant`: stand one of a block's trees, in the grove or a proposed layout of it."""

__lazy_modules__ = ["lemonaid.grove.source"]

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from ..config import load_config
from . import layout_cli
from .layout import edit, state, tangles
from .model import Block
from .source import live
from .tui.frame import Grove


def _fail(args: argparse.Namespace, error: str) -> NoReturn:
    if args.json:
        print(json.dumps({"error": error}))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(1)


def _block(args: argparse.Namespace) -> tuple[Grove, Block, Path | None]:
    """The grove, laid out into the `--layout` file if there is one, and the block BLOCK names."""
    where = layout_cli.proposed(args, args.layout) if args.layout else None
    grove = live.fresh(load_config(), None, where=where)
    found = next((b for b in grove.blocks if args.block in (b.digit, b.name)), None)
    if found is None:
        _fail(args, f"No block {args.block}; blocks are {', '.join(b.digit for b in grove.blocks)}")
    if grove.arrangement.plots[found.name].texture == "house":
        _fail(args, "The packhouse's bays stay in order")
    return grove, found, where


def _save(args: argparse.Namespace, grove: Grove, block: Block, where: Path | None, spots) -> None:
    try:
        state.update(lambda saved: tangles.plant(grove.blocks, saved, block, spots), where)
    except edit.EditError as error:
        _fail(args, str(error))


def _cmd_plant(args: argparse.Namespace) -> None:
    grove, block, where = _block(args)
    found = next(
        (
            t
            for t in block.trees
            if args.tree in (t.key, grove.arrangement.trees[(block.name, t.key)].letter)
        ),
        None,
    )
    if found is None:
        _fail(args, f"No tree {args.tree!r} in block {block.digit}; give its letter or key")
    _save(args, grove, block, where, {found.key: (args.x, args.y)})
    letter = grove.arrangement.trees[(block.name, found.key)].letter
    if args.json:
        print(json.dumps({"tree": found.key, "spot": [args.x, args.y], "error": None}))
    else:
        print(f"Block {block.digit}: tree {letter} at {args.x},{args.y}")


def add_parsers(grove_subparsers: argparse._SubParsersAction) -> None:
    def tree_parser(name: str, help_text: str) -> argparse.ArgumentParser:
        parser = grove_subparsers.add_parser(name, help=help_text)
        parser.add_argument("block", help="A block's digit or its group's name")
        parser.add_argument("--json", action="store_true", help="Print the result as JSON")
        parser.add_argument(
            "--layout",
            type=Path,
            metavar="FILE",
            help="Change the proposed layout in FILE (from `grove propose`), not the live grove",
        )
        return parser

    plant = tree_parser("plant", "Stand one of a block's trees at X, Y within its plot")
    plant.add_argument("tree", help="The tree's letter, as the grove shows it, or its key")
    plant.add_argument("x", type=int)
    plant.add_argument("y", type=int)
    plant.set_defaults(func=_cmd_plant)
